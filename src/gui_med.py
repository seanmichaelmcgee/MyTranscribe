"""
gui_med.py — MyTranscribe "Medical / GTX 1060 edition".

A separate entry point alongside gui_qt.py (which is unchanged in behaviour).
Same window, buttons, chimes and Ctrl+Alt+Q hotkey; different engine:

  * faster-whisper (CTranslate2) with an auto-picked model/compute type —
    large-v3-turbo int8 on a GTX 1060 (see hw_profile.py). No PyTorch.
  * Audio is chunked and transcribed in the background *while you dictate*,
    kept in RAM only (chunked_transcriber.py). Stop never freezes the window.
  * Model loads in a background thread at startup; buttons enable when ready.
  * Medical vocabulary: a style example (prompts/medical_prompt.txt) plus
    topic-aware term lists (vocab/primary_care.txt) chosen per chunk from
    what you're dictating, and conservative spelling correction of
    near-miss drug/term names (vocab.py, vocab_correct.py).
  * Transcript text is never logged; clipboard copies opt out of Windows
    clipboard history / cloud sync (phi_clipboard.py).
  * Every copy is verified. If another program holds the clipboard, the
    copy is retried for ~0.5 s; if it still fails, the window says "Not
    copied" and nothing is auto-pasted (the clipboard would still hold the
    previous text).
  * Start/stop: big on-screen button, Space (window focused), Ctrl+Alt+Q,
    plus F9 (hold to talk) and the mouse "forward" button (toggle) anywhere
    (triggers.py). Hotkeys never pull the window to the front: it stays on
    top, and keyboard focus stays in your EMR for Ctrl+V.
  * A round light, always visible: green = recording, red = not recording.
    Starts in compact view (+ shows the transcript). The ⚙ Options screen
    (options_dialog.py) changes the keys and hold/toggle; saved by settings.py.
  * Optional auto-paste: set MYTRANSCRIBE_AUTOPASTE=1 and, after a hotkey
    stop, the text is pasted into whatever window has focus (your EMR /
    Word).

Run: python src/gui_med.py   (or run_1060.bat on Windows)
"""

import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

_SRC_DIR = Path(__file__).parent
sys.path.insert(0, str(_SRC_DIR))

from fw_engine import register_cuda_dll_dirs                 # noqa: E402
from hw_profile import choose_config, detect_hardware        # noqa: E402
from chunked_transcriber import ChunkedTranscriber           # noqa: E402
from prompt_loader import load_prompt                        # noqa: E402
from vocab import build_text_pipeline                        # noqa: E402
import phi_clipboard                                         # noqa: E402
from gui_qt import AppState, TranscriptionWindow             # noqa: E402
from triggers import InputTriggers                           # noqa: E402
import settings as settings_store                            # noqa: E402
import voice_commands                                        # noqa: E402
from options_dialog import OptionsDialog                     # noqa: E402

logger = logging.getLogger("gui_med")

WINDOW_TITLE_MED = "MyTranscribe — Medical"
LOAD_POLL_MS = 200
AUTOPASTE_DELAY_MS = 150        # let the target window settle after the hotkey
AUTOPASTE_RETRY_MS = 50         # re-check modifier keys this often...
AUTOPASTE_MAX_WAIT_MS = 3000    # ...for at most this long, then paste anyway
COPY_ATTEMPTS = 6               # clipboard busy (EMR / Citrix)? retry...
COPY_RETRY_MS = 100             # ...this often (~0.5 s total) before giving up
LOADING_TEXT = "Loading speech model… (first run downloads ~1.6 GB)"
TRANSCRIBING_SUFFIX = "\n\n[Finishing transcription…]"
NORMAL_SIZE = (560, 300)
COMPACT_WIDTH = 380

# Recording light: always visible, green = recording, red = not recording.
REC_ON_COLOUR = "#2E9E4F"
REC_OFF_COLOUR = "#C8322B"
# Status text colour per kind.
STATUS_COLOURS = {"idle": "#5E5D59", "recording": "#1F6E37", "busy": "#5E5D59",
                  "ok": "#3B6347", "warn": "#93370D"}

# Warm, Claude-desktop-like light theme. Replaces gui_qt.APP_QSS for this window.
MED_QSS = """
QMainWindow, QWidget#medRoot { background: #F5F4ED; }
QWidget { font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: #1F1E1D; }
QTextEdit#transcriptionView {
    background: #FFFFFF; border: 1px solid #E3E1D7; border-radius: 10px;
    padding: 8px 10px; font-size: 11pt; selection-background-color: #F0D9CD; selection-color: #1F1E1D;
}
QLabel#statusText { font-weight: 600; }
QLabel#recLight { border-radius: 9px; border: 1px solid rgba(0, 0, 0, 0.15); }
QPushButton { border-radius: 8px; padding: 6px 12px; }
QPushButton#toggleButton {
    background: #C96442; color: #FFFFFF; border: none; font-size: 11pt; font-weight: 600; min-height: 34px;
}
QPushButton#toggleButton:hover { background: #B5583A; }
QPushButton#toggleButton:pressed { background: #A14E33; }
QPushButton#toggleButton[recording="true"] { background: #2F2E2A; }
QPushButton#toggleButton[recording="true"]:hover { background: #1F1E1D; }
QPushButton#toggleButton:disabled { background: #E6CDC1; color: #FFFFFF; }
QPushButton#copyButton, QPushButton#compactButton, QPushButton#optionsButton {
    background: transparent; color: #3D3C38; border: 1px solid #DAD8CD;
}
QPushButton#compactButton, QPushButton#optionsButton { padding: 6px 9px; }
QPushButton#optionsButton { font-family: "Segoe UI Symbol"; font-size: 12pt; padding: 3px 8px; }
QPushButton#copyButton:hover, QPushButton#compactButton:hover, QPushButton#optionsButton:hover {
    background: #ECEADF;
}
QPushButton#copyButton:disabled { color: #B4B2A9; border-color: #E6E4DA; }
QPushButton#copyButton[attention="true"] { background: #FCEFE6; color: #93370D; border-color: #E9B48F; }
QFrame#audioIndicator { background: #C96442; border-radius: 2px; border: none; }
"""


def env_flag(name: str, env: Optional[dict] = None) -> bool:
    """True for 1/true/yes/on (case-insensitive)."""
    env = os.environ if env is None else env
    return env.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def build_default_engine(accurate: bool = True):
    """Detect hardware, pick a config, load + warm up faster-whisper."""
    from fw_engine import FasterWhisperEngine
    hw = detect_hardware()
    cfg = choose_config(hw, accurate=accurate)
    logger.info("Engine config: model=%s device=%s compute=%s threads=%d (%s)",
                cfg.model, cfg.device, cfg.compute_type, cfg.cpu_threads, cfg.reason)
    engine = FasterWhisperEngine(cfg)
    engine.warmup()
    return engine


class MedTranscriptionWindow(TranscriptionWindow):
    """
    TranscriptionWindow with the background faster-whisper pipeline.

    engine_factory / stream_factory / autopaste / settings / settings_path are
    injectable for tests; install_hooks=False never installs the global F9 /
    mouse hooks (the trigger logic still works via self._triggers.handle()).
    """

    def __init__(self, engine_factory: Optional[Callable] = None,
                 stream_factory: Optional[Callable] = None,
                 autopaste: Optional[bool] = None,
                 base_prompt: Optional[str] = None,
                 text_pipeline: Optional[tuple] = None,
                 settings: Optional["settings_store.Settings"] = None,
                 settings_path: Optional[Path] = None,
                 install_hooks: bool = True) -> None:
        self._stream_factory = stream_factory
        self._autopaste = env_flag("MYTRANSCRIBE_AUTOPASTE") if autopaste is None else autopaste
        self._base_prompt = load_prompt() if base_prompt is None else base_prompt
        self._settings_path = settings_path
        self._settings = settings if settings is not None else settings_store.load(settings_path)
        accurate = self._settings.accuracy == "best"
        self._engine_factory = engine_factory or (lambda: build_default_engine(accurate))
        self._install_hooks = install_hooks
        self._engine = None
        self._text_pipeline = text_pipeline    # (prompt_builder, corrector); built on load if None
        self._load_error: Optional[str] = None
        self._finishing = False
        self._finish_from_hotkey = False
        self._paste_waited_ms = 0
        self._copy_generation = 0      # bumps on every new copy; stale retries give up
        self._copied_text: Optional[str] = None   # what we last verified on the clipboard
        self._clipboard_seq = phi_clipboard.windows_clipboard_sequence()   # tests set None
        self._copied_seq: Optional[int] = None    # clipboard sequence number right after our copy
        self._compact = False
        self.paste_count = 0           # for tests / diagnostics
        self.copy_ok: Optional[bool] = None

        super().__init__()
        self.setWindowTitle(WINDOW_TITLE_MED + (" [auto-paste]" if self._autopaste else ""))
        self.setWindowOpacity(1.0)
        self.setMinimumSize(COMPACT_WIDTH, 0)      # height: whatever the visible rows need
        self.resize(*NORMAL_SIZE)

        self._triggers = None
        self._apply_triggers()
        self._set_rec_light(False)
        if self._settings.start_compact:
            self._toggle_compact()

        # Background model load; buttons stay disabled until it finishes.
        self._set_buttons_enabled(False)
        self._text_area.setPlainText(LOADING_TEXT)
        self._load_thread = threading.Thread(target=self._load_engine, name="model-load", daemon=True)
        self._load_thread.start()
        self._load_timer = QTimer(self)
        self._load_timer.setInterval(LOAD_POLL_MS)
        self._load_timer.timeout.connect(self._check_load)
        self._load_timer.start()

    # ── Model loading ─────────────────────────────────────────────────────────
    def _load_engine(self) -> None:
        """Runs on the model-load thread. Never touches widgets."""
        try:
            self._engine = self._engine_factory()
            if self._text_pipeline is None:
                self._text_pipeline = build_text_pipeline(
                    self._base_prompt, count=getattr(self._engine, "count_tokens", None))
        except Exception as exc:
            logger.error("Model load failed", exc_info=True)
            self._load_error = str(exc) or exc.__class__.__name__

    def _check_load(self) -> None:
        if self._load_thread.is_alive():
            return
        self._load_timer.stop()
        if self._load_error:
            self._text_area.setPlainText(
                f"Could not load the speech model:\n{self._load_error}\n\n"
                "Check the console log; see README_1060.md → Troubleshooting."
            )
            self._set_status("Model failed to load", "warn")
            return
        builder, corrector = self._text_pipeline
        self._transcriber = ChunkedTranscriber(
            self._engine, self._base_prompt, stream_factory=self._stream_factory,
            prompt_builder=builder, postprocess=corrector,
        )
        logger.info("Topic prompts %s, spelling correction %s",
                    "on" if builder else "off", "on" if corrector else "off")
        self._device = getattr(getattr(self._engine, "config", None), "device", None)
        self._text_area.setPlainText("")
        self._set_buttons_enabled(True)
        self._set_status("Ready", "idle")
        logger.info("Ready")

    @property
    def ready(self) -> bool:
        return self._transcriber is not None

    def _ensure_model_loaded(self) -> None:
        """Model loads at startup in the background; nothing to do here."""

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._start_btn.setEnabled(enabled)
        self._long_btn.setEnabled(enabled)
        self._stop_btn.setEnabled(False)
        self._refresh_controls()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        """
        Status row (recording light), transcript, one big Start/Stop button.

        _start_btn / _stop_btn are kept (hidden) because the shared state
        machine in gui_qt enables/disables them; the visible toggle button
        mirrors their state in _refresh_controls().
        """
        root = QWidget()
        root.setObjectName("medRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Status row: (light) Ready ..................... [Copy] [⚙] [–]
        top = QHBoxLayout()
        top.setSpacing(6)
        self._rec_light = QLabel()
        self._rec_light.setObjectName("recLight")
        self._rec_light.setFixedSize(18, 18)
        self._status_text = QLabel("Loading…")
        self._status_text.setObjectName("statusText")
        top.addWidget(self._rec_light)
        top.addSpacing(2)
        top.addWidget(self._status_text)
        top.addStretch(1)
        self._copy_btn = self._small_button("Copy", "copyButton", self._on_copy_clicked,
                                            "Copy the transcript again")
        self._options_btn = self._small_button("⚙", "optionsButton", self._open_options,
                                               "Options: keys, hold-to-talk, help")
        self._compact_btn = self._small_button("–", "compactButton", self._toggle_compact,
                                               "Compact view (button only)")
        for b in (self._copy_btn, self._options_btn, self._compact_btn):
            top.addWidget(b)
        layout.addLayout(top)

        self._text_area = QTextEdit()
        self._text_area.setObjectName("transcriptionView")
        self._text_area.setReadOnly(True)
        self._text_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._text_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        layout.addWidget(self._text_area, stretch=1)

        self._audio_indicator = QFrame(self._text_area.viewport())
        self._audio_indicator.setObjectName("audioIndicator")
        self._audio_indicator.setFixedSize(40, 4)
        self._audio_indicator.setVisible(False)
        self._reposition_indicator()

        row = QHBoxLayout()
        row.setSpacing(8)
        self._toggle_btn = QPushButton("Start dictation")
        self._toggle_btn.setObjectName("toggleButton")
        self._toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # Space must not click it
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)
        row.addWidget(self._toggle_btn)
        layout.addLayout(row)

        # State holders for the shared gui_qt state machine (never shown). There is
        # no Long record button here: chunked background transcription already
        # handles any length up to MAX_SESSION_S with live text.
        self._start_btn = QPushButton(root)
        self._stop_btn = QPushButton(root)
        self._long_btn = QPushButton(root)
        for b in (self._start_btn, self._stop_btn, self._long_btn):
            b.hide()
        self._stop_btn.setEnabled(False)

    def _small_button(self, text: str, name: str, slot: Callable, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName(name)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def _set_status(self, text: str, kind: str) -> None:
        self._status_text.setStyleSheet(f"color: {STATUS_COLOURS[kind]};")
        self._status_text.setText(text)

    def _set_rec_light(self, recording: bool) -> None:
        """Green = recording, red = not recording. Visible in every view."""
        self.rec_light_on = recording
        self._rec_light.setStyleSheet(f"background: {REC_ON_COLOUR if recording else REC_OFF_COLOUR};")
        self._rec_light.setToolTip("Recording" if recording else "Not recording")

    def _refresh_controls(self) -> None:
        """Mirror the state machine onto the visible toggle / copy buttons."""
        recording = self._state in (AppState.NORMAL_RECORDING, AppState.LONG_RECORDING)
        btn = self._toggle_btn
        if recording:
            btn.setText("Stop")
        elif self._finishing:
            btn.setText("Finishing…")
        elif not self.ready:
            btn.setText("Loading model…")
        else:
            btn.setText("Start dictation")
        btn.setEnabled(self._stop_btn.isEnabled() if recording else self._start_btn.isEnabled())
        if btn.property("recording") != recording:
            btn.setProperty("recording", recording)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._copy_btn.setEnabled(not recording and not self._finishing
                                  and bool(self._text_area.toPlainText().strip()) and self.ready)
        # Saving Options rebuilds the F9 / mouse hooks: never mid-recording (a held
        # F9 would lose its release).
        self._options_btn.setEnabled(not recording and not self._finishing)

    def _set_copy_attention(self, on: bool) -> None:
        if self._copy_btn.property("attention") != on:
            self._copy_btn.setProperty("attention", on)
            self._copy_btn.style().unpolish(self._copy_btn)
            self._copy_btn.style().polish(self._copy_btn)

    def _set_state(self, new_state: AppState) -> None:
        super()._set_state(new_state)
        self._set_rec_light(new_state in (AppState.NORMAL_RECORDING, AppState.LONG_RECORDING))
        if new_state == AppState.NORMAL_RECORDING:
            self._set_status("Recording", "recording")
        elif new_state == AppState.LONG_RECORDING:
            self._set_status("Recording (long)", "recording")
        self._set_copy_attention(False)
        self._refresh_controls()

    def _toggle_compact(self) -> None:
        """Hide/show the transcript. Compact keeps the light, status and buttons."""
        self._compact = not self._compact
        self._compact_btn.setText("+" if self._compact else "–")
        self._compact_btn.setToolTip("Show transcript" if self._compact else "Compact view (button only)")
        if self._compact:
            if self.isVisible():
                self._normal_size = (self.width(), self.height())
            self._text_area.setVisible(False)
            self._fit_compact()
            QTimer.singleShot(0, self._fit_compact)    # again once the layout has settled
        else:
            self._text_area.setVisible(True)
            self.resize(*getattr(self, "_normal_size", NORMAL_SIZE))

    def _fit_compact(self) -> None:
        """Shrink to exactly the visible rows (an explicit minimum height would clip them)."""
        if not self._compact:
            return
        self.centralWidget().layout().invalidate()
        self.centralWidget().layout().activate()
        self.resize(max(COMPACT_WIDTH, min(self.width(), 420)), self.minimumSizeHint().height())

    # ── Start / stop ──────────────────────────────────────────────────────────
    def _can_start(self) -> bool:
        return self._state == AppState.IDLE and self.ready and not self._finishing

    def _start(self, mode: str, state: AppState) -> None:
        if not self._can_start():
            return
        try:
            self._transcriber.start_recording(mode=mode)
        except (OSError, RuntimeError) as exc:
            logger.error("Could not start recording: %s", exc)
            self._text_area.setPlainText(f"Could not open the microphone:\n{exc}")
            return
        self._text_area.setPlainText("")
        self._copy_generation += 1      # cancel any pending copy retries
        self._set_state(state)          # plays start chime
        self._poll_timer.start()

    def _start_normal(self) -> None:
        self._start("normal", AppState.NORMAL_RECORDING)

    def _start_long(self) -> None:
        self._start("long", AppState.LONG_RECORDING)

    def _stop_recording(self, from_hotkey: bool = False) -> None:
        """Recording → Idle immediately; transcription of the tail continues in the background."""
        if self._state == AppState.IDLE:
            return
        self._set_state(AppState.IDLE)  # end chime, hides indicator
        self._transcriber.stop_recording()
        self._finishing = True
        self._finish_from_hotkey = from_hotkey
        self._set_buttons_enabled(False)
        self._set_status("Transcribing…", "busy")
        self._text_area.setPlainText(self._display_text() + TRANSCRIBING_SUFFIX)
        self._poll_timer.start()        # keep polling until the worker drains

    def _poll_tick(self) -> None:
        t = self._transcriber
        if self._finishing:
            if t.busy:
                self._text_area.setPlainText(self._display_text() + TRANSCRIBING_SUFFIX)
                return
            self._poll_timer.stop()
            self._finishing = False
            self._finalize(self._display_text(), self._finish_from_hotkey)
            self._set_buttons_enabled(True)
            return

        if self._state in (AppState.NORMAL_RECORDING, AppState.LONG_RECORDING) and not t.recording:
            # Capture ended on its own (1 h cap or microphone failure).
            if t.capture_error:
                logger.error("Recording ended: %s", t.capture_error)
            self._stop_recording(from_hotkey=False)
            return

        if self._state == AppState.LONG_RECORDING:
            self._text_area.setPlainText("Recording in long mode...")
        elif self._state == AppState.NORMAL_RECORDING:
            text = self._display_text()
            if self._text_area.toPlainText() != text:   # avoid resetting scroll every 30 ms
                self._text_area.setPlainText(text)
        else:
            self._poll_timer.stop()
            return
        self._audio_indicator.setVisible(t.audio_detected)
        self._reposition_indicator()

    def _finalize(self, text: str, from_hotkey: bool) -> None:
        """Show final text, copy it (PHI-safe, verified), optionally auto-paste."""
        if self._transcriber.capture_error:
            text = (text + "\n\n" if text else "") + f"[{self._transcriber.capture_error}]"
        if not text:
            logger.info("Empty transcription — preserving previous clipboard")
            self._text_area.setPlainText("")
            self._set_status("Nothing heard", "idle")
            return
        self._text_area.setPlainText(text)
        self._copy(text, paste=self._autopaste and from_hotkey)

    def _display_text(self) -> str:
        """Transcript so far, with spoken formatting commands applied if enabled."""
        text = self._transcriber.text
        return voice_commands.apply(text) if self._settings.voice_commands else text

    # ── Clipboard: verified copy, then (maybe) paste ──────────────────────────
    def _clipboard(self):
        """The system clipboard (tests swap in a fake)."""
        return QApplication.instance().clipboard()

    def _copy(self, text: str, paste: bool) -> None:
        self._copy_generation += 1
        self._copied_text = None
        self._try_copy(text, paste, self._copy_generation, attempt=1)

    def _try_copy(self, text: str, paste: bool, generation: int, attempt: int) -> None:
        if generation != self._copy_generation:
            return                      # superseded by a newer copy or recording
        if phi_clipboard.copy_text(self._clipboard(), text, sequence=self._clipboard_seq):
            self._copied_text = text
            self._copied_seq = self._clipboard_seq() if self._clipboard_seq else None
            self.copy_ok = True
            logger.info("Copied %d chars to clipboard", len(text))   # length only: no PHI in logs
            self._set_copy_attention(False)
            self._set_status("Copied — paste with Ctrl+V", "ok")
            if paste:
                self._paste_waited_ms = 0
                QTimer.singleShot(AUTOPASTE_DELAY_MS, self._try_paste)
            return
        if attempt < COPY_ATTEMPTS:
            QTimer.singleShot(COPY_RETRY_MS, lambda: self._try_copy(text, paste, generation, attempt + 1))
            return
        # The clipboard still holds the PREVIOUS contents: never paste now.
        self.copy_ok = False
        logger.warning("Clipboard busy: copy failed after %d attempts; not pasting", attempt)
        self._set_copy_attention(True)
        self._set_status("Not copied — clipboard busy. Click Copy", "warn")

    def _try_paste(self) -> None:
        if phi_clipboard.modifiers_held() and self._paste_waited_ms < AUTOPASTE_MAX_WAIT_MS:
            self._paste_waited_ms += AUTOPASTE_RETRY_MS
            QTimer.singleShot(AUTOPASTE_RETRY_MS, self._try_paste)
            return
        # Re-check right before pasting: something else may have taken the clipboard.
        # On Windows the sequence number answers that without a (possibly blocking) read.
        if self._clipboard_seq is not None:
            unchanged = self._copied_seq is not None and self._clipboard_seq() == self._copied_seq
        else:
            try:
                unchanged = self._copied_text is not None and self._clipboard().text() == self._copied_text
            except Exception:
                unchanged = False
        if self._copied_text is None or not unchanged:
            logger.warning("Clipboard changed before auto-paste; not pasting")
            self._set_status("Not pasted — clipboard changed. Click Copy", "warn")
            self._set_copy_attention(True)
            return
        try:
            phi_clipboard.send_paste()
            self.paste_count += 1
            self._set_status("Pasted", "ok")
        except Exception as exc:
            logger.error("Auto-paste failed: %s", exc)

    def _on_copy_clicked(self) -> None:
        text = self._text_area.toPlainText().strip()
        if text and not self._finishing and self._state == AppState.IDLE:
            self._copy(text, paste=False)

    # ── Input handlers ────────────────────────────────────────────────────────
    def _on_space_pressed(self) -> None:
        if self._finishing or not self.ready:
            return
        super()._on_space_pressed()

    def _on_toggle_clicked(self) -> None:
        if self._state == AppState.IDLE:
            self._on_start_clicked()
        else:
            self._on_stop_clicked()

    def on_hotkey(self) -> None:
        """Ctrl+Alt+Q / F9 / mouse button (toggle mode)."""
        if self._finishing or not self.ready:
            return
        if self._state == AppState.IDLE:
            # Don't raise the window (it's always on top anyway): keyboard focus
            # stays in the EMR, ready for Ctrl+V or auto-paste.
            self._start_normal()
            return
        super().on_hotkey()

    # ── F9 / mouse triggers and Options ───────────────────────────────────────
    def _apply_triggers(self) -> None:
        """(Re)create the F9 / mouse triggers from the current settings."""
        if self._triggers is not None:
            try:
                self._triggers.stop()
            except Exception:
                pass
            self._triggers.deleteLater()
        self._triggers = InputTriggers(self._settings.triggers(), parent=self)
        self._triggers.pressed.connect(self._on_trigger_pressed, Qt.ConnectionType.QueuedConnection)
        self._triggers.released.connect(self._on_trigger_released, Qt.ConnectionType.QueuedConnection)
        if self._install_hooks:
            try:
                self._triggers.start()
            except Exception as exc:          # never let an input hook stop the app
                logger.error("Could not start F9 / mouse triggers: %s", exc)

    def _on_trigger_pressed(self, source: str) -> None:
        hold = self._triggers.config.hold_for(source)
        if hold and self._state != AppState.IDLE:
            return                      # hold-to-talk: a press only ever starts
        self.on_hotkey()

    def _on_trigger_released(self, source: str) -> None:
        if self._triggers.config.hold_for(source) and self._state == AppState.NORMAL_RECORDING:
            self.on_hotkey()

    def _open_options(self) -> None:
        dlg = OptionsDialog(self._settings, parent=self)
        if dlg.exec():
            self.apply_settings(dlg.result_settings())

    def apply_settings(self, new: "settings_store.Settings") -> None:
        """Save and apply edited options (start_compact only affects the next start)."""
        self._settings = new.clean()
        settings_store.save(self._settings, self._settings_path)
        self._apply_triggers()

    def closeEvent(self, event) -> None:
        if self._triggers is not None:
            try:
                self._triggers.stop()
            except Exception:
                pass
        if self._transcriber is not None:
            try:
                self._transcriber.cleanup()
            except Exception:
                pass
        self._state = AppState.IDLE     # base closeEvent must not stop twice
        super().closeEvent(event)


def main() -> None:
    os.chdir(Path(__file__).parent)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    register_cuda_dll_dirs()            # before ctranslate2 touches CUDA (Windows)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("MyTranscribe Medical")
    app.setStyleSheet(MED_QSS)
    logger.info("Starting MyTranscribe Medical (faster-whisper); hotkey Ctrl+Alt+Q")

    window = MedTranscriptionWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

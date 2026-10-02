"""
gui_med.py — MyTranscribe "Medical / GTX 1060 edition".

A separate entry point alongside gui_qt.py (which is unchanged in behaviour).
Same window, buttons, chimes and Ctrl+Alt+Q hotkey; different engine:

  * faster-whisper (CTranslate2) with an auto-picked model/compute type —
    large-v3-turbo int8 on a GTX 1060 (see hw_profile.py). No PyTorch.
  * Audio is chunked and transcribed in the background *while you dictate*,
    kept in RAM only (chunked_transcriber.py). Stop never freezes the window.
  * Model loads in a background thread at startup; buttons enable when ready.
  * Medical vocabulary prompt (prompts/medical_prompt.txt, editable).
  * Transcript text is never logged; clipboard copies opt out of Windows
    clipboard history / cloud sync (phi_clipboard.py).
  * Optional auto-paste: set MYTRANSCRIBE_AUTOPASTE=1 and, after a hotkey
    stop, the text is pasted into whatever window has focus (your EMR /
    Word). In this mode the hotkey does NOT pull the MyTranscribe window to
    the front, so focus stays where you were typing.

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
from PyQt6.QtWidgets import QApplication

_SRC_DIR = Path(__file__).parent
sys.path.insert(0, str(_SRC_DIR))

from fw_engine import register_cuda_dll_dirs                 # noqa: E402
from hw_profile import choose_config, detect_hardware        # noqa: E402
from chunked_transcriber import ChunkedTranscriber           # noqa: E402
from prompt_loader import load_prompt                        # noqa: E402
import phi_clipboard                                         # noqa: E402
from gui_qt import APP_QSS, AppState, TranscriptionWindow    # noqa: E402

logger = logging.getLogger("gui_med")

WINDOW_TITLE_MED = "MyTranscribe — Medical"
LOAD_POLL_MS = 200
AUTOPASTE_DELAY_MS = 150        # let the target window settle after the hotkey
AUTOPASTE_RETRY_MS = 50         # re-check modifier keys this often...
AUTOPASTE_MAX_WAIT_MS = 3000    # ...for at most this long, then paste anyway
LOADING_TEXT = "Loading speech model… (first run downloads ~1.6 GB)"
TRANSCRIBING_SUFFIX = "\n\n[Finishing transcription…]"


def env_flag(name: str, env: Optional[dict] = None) -> bool:
    """True for 1/true/yes/on (case-insensitive)."""
    env = os.environ if env is None else env
    return env.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def build_default_engine():
    """Detect hardware, pick a config, load + warm up faster-whisper."""
    from fw_engine import FasterWhisperEngine
    hw = detect_hardware()
    cfg = choose_config(hw)
    logger.info("Engine config: model=%s device=%s compute=%s threads=%d (%s)",
                cfg.model, cfg.device, cfg.compute_type, cfg.cpu_threads, cfg.reason)
    engine = FasterWhisperEngine(cfg)
    engine.warmup()
    return engine


class MedTranscriptionWindow(TranscriptionWindow):
    """
    TranscriptionWindow with the background faster-whisper pipeline.

    engine_factory / stream_factory / autopaste are injectable for tests.
    """

    def __init__(self, engine_factory: Optional[Callable] = None,
                 stream_factory: Optional[Callable] = None,
                 autopaste: Optional[bool] = None,
                 base_prompt: Optional[str] = None) -> None:
        self._engine_factory = engine_factory or build_default_engine
        self._stream_factory = stream_factory
        self._autopaste = env_flag("MYTRANSCRIBE_AUTOPASTE") if autopaste is None else autopaste
        self._base_prompt = load_prompt() if base_prompt is None else base_prompt
        self._engine = None
        self._load_error: Optional[str] = None
        self._finishing = False
        self._finish_from_hotkey = False
        self._paste_waited_ms = 0
        self.paste_count = 0           # for tests / diagnostics

        super().__init__()
        self.setWindowTitle(WINDOW_TITLE_MED + (" [auto-paste]" if self._autopaste else ""))

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
            return
        self._transcriber = ChunkedTranscriber(
            self._engine, self._base_prompt, stream_factory=self._stream_factory,
        )
        self._device = getattr(getattr(self._engine, "config", None), "device", None)
        self._text_area.setPlainText("")
        self._set_buttons_enabled(True)
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
        self._text_area.setPlainText(self._transcriber.text + TRANSCRIBING_SUFFIX)
        self._poll_timer.start()        # keep polling until the worker drains

    def _poll_tick(self) -> None:
        t = self._transcriber
        if self._finishing:
            if t.busy:
                self._text_area.setPlainText(t.text + TRANSCRIBING_SUFFIX)
                return
            self._poll_timer.stop()
            self._finishing = False
            self._set_buttons_enabled(True)
            self._finalize(t.text, self._finish_from_hotkey)
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
            text = t.text
            if self._text_area.toPlainText() != text:   # avoid resetting scroll every 30 ms
                self._text_area.setPlainText(text)
        else:
            self._poll_timer.stop()
            return
        self._audio_indicator.setVisible(t.audio_detected)
        self._reposition_indicator()

    def _finalize(self, text: str, from_hotkey: bool) -> None:
        """Show final text, copy it (PHI-safe), optionally auto-paste."""
        if self._transcriber.capture_error:
            text = (text + "\n\n" if text else "") + f"[{self._transcriber.capture_error}]"
        if not text:
            logger.info("Empty transcription — preserving previous clipboard")
            self._text_area.setPlainText("")
            return
        self._text_area.setPlainText(text)
        phi_clipboard.copy_text(QApplication.instance().clipboard(), text)
        logger.info("Copied %d chars to clipboard", len(text))   # length only: no PHI in logs
        if self._autopaste and from_hotkey:
            self._paste_waited_ms = 0
            QTimer.singleShot(AUTOPASTE_DELAY_MS, self._try_paste)

    def _try_paste(self) -> None:
        if phi_clipboard.modifiers_held() and self._paste_waited_ms < AUTOPASTE_MAX_WAIT_MS:
            self._paste_waited_ms += AUTOPASTE_RETRY_MS
            QTimer.singleShot(AUTOPASTE_RETRY_MS, self._try_paste)
            return
        try:
            phi_clipboard.send_paste()
            self.paste_count += 1
        except Exception as exc:
            logger.error("Auto-paste failed: %s", exc)

    # ── Input handlers ────────────────────────────────────────────────────────
    def _on_space_pressed(self) -> None:
        if self._finishing or not self.ready:
            return
        super()._on_space_pressed()

    def on_hotkey(self) -> None:
        if self._finishing or not self.ready:
            return
        if self._state == AppState.IDLE and self._autopaste:
            # Keep keyboard focus in the user's target app for the later paste.
            self._start_normal()
            return
        super().on_hotkey()

    def closeEvent(self, event) -> None:
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
    app.setStyleSheet(APP_QSS)
    logger.info("Starting MyTranscribe Medical (faster-whisper); hotkey Ctrl+Alt+Q")

    window = MedTranscriptionWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

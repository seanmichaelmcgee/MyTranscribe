"""
gui_qt.py — PyQt6 GUI for MyTranscribe (Windows port, Phase 4).

Replaces src/gui-v0.8.py (GTK3/Linux). Feature-parity with the GTK original,
including the global Ctrl+Alt+Q hotkey via pynput (Phase 4).

Controls: mouse clicks, spacebar, and global Ctrl+Alt+Q hotkey.
Architecture:
  - Single QMainWindow (TranscriptionWindow).
  - Whisper inference runs in a plain threading.Thread (owned by RealTimeTranscriber).
  - Audio indicator and text area are polled every 30 ms by a QTimer on the GUI thread.
  - All widget access happens on the GUI thread (no QThread, no lock-free writes to Qt).
  - HotkeyBridge owns the pynput Listener; it emits hotkey_pressed via pyqtSignal
    using QueuedConnection so the slot always runs on the GUI thread (Risk R08, R23).
"""

import sys
import os
import signal
import logging
import threading
from pathlib import Path
from enum import Enum, auto

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QFrame,
)
from PyQt6.QtCore import (
    Qt, QObject, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QKeyEvent, QShortcut, QKeySequence

import torch
import whisper

# pynput is imported for the Phase 4 HotkeyBridge stub; harmless to import now.
from pynput import keyboard as pynput_keyboard

# ── Project-local imports ────────────────────────────────────────────────────
# Resolve via __file__ so the import works regardless of cwd (Risk R15).
_SRC_DIR = Path(__file__).parent
sys.path.insert(0, str(_SRC_DIR))
from transcriber_v12 import RealTimeTranscriber   # noqa: E402
from sound_utils import ChimePlayer               # noqa: E402

# ── Logging ──────────────────────────────────────────────────────────────────
# Set stdout to UTF-8 so non-ASCII transcripts don't crash the log (Risk R26).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gui_qt")

# ── Constants ────────────────────────────────────────────────────────────────
WINDOW_TITLE             = "Real-Time Transcription"
WINDOW_W                 = 650
WINDOW_H                 = 200
WINDOW_MIN_W             = 400
WINDOW_MIN_H             = 150
WINDOW_OPACITY           = 0.9
POLL_INTERVAL_MS         = 30       # §6.2 — do not change to "save CPU"
HOTKEY_CLIPBOARD_DELAY_MS = 150     # Risk R09 / R-arch-B: delay clipboard write
                                    # when triggered by hotkey (modifiers still held)
WHISPER_MODEL            = "small"
LONG_MODE_PLACEHOLDER    = "Recording in long mode..."

# ── QSS Stylesheet ───────────────────────────────────────────────────────────
APP_QSS = """
/* ── Start button ── */
QPushButton#startButton {
    background-color: #00FF00;
    color: black;
    font-weight: bold;
    border: 1px solid #00CC00;
    border-radius: 3px;
    padding: 4px 8px;
}
QPushButton#startButton:hover {
    background-color: #33FF33;
}
QPushButton#startButton:pressed {
    background-color: #00CC00;
}
QPushButton#startButton:disabled {
    background-color: #99CC99;
    color: #555555;
}

/* ── Stop button ── */
QPushButton#stopButton {
    background-color: #FF0000;
    color: black;
    font-weight: bold;
    border: 1px solid #CC0000;
    border-radius: 3px;
    padding: 4px 8px;
}
QPushButton#stopButton:hover {
    background-color: #FF3333;
}
QPushButton#stopButton:pressed {
    background-color: #CC0000;
}
QPushButton#stopButton:disabled {
    background-color: #CC9999;
    color: #555555;
}

/* ── Long Record button ── */
QPushButton#longButton {
    background-color: #0000FF;
    color: black;
    font-weight: bold;
    border: 1px solid #0000CC;
    border-radius: 3px;
    padding: 4px 8px;
}
QPushButton#longButton:hover {
    background-color: #3333FF;
}
QPushButton#longButton:pressed {
    background-color: #0000CC;
}
QPushButton#longButton:disabled {
    background-color: #9999CC;
    color: #555555;
}

/* ── Audio activity indicator ── */
QFrame#audioIndicator {
    background-color: #00AA00;
    border-radius: 2px;
    border: none;
}
"""


# ── AppState enum ─────────────────────────────────────────────────────────────
class AppState(Enum):
    IDLE             = auto()
    NORMAL_RECORDING = auto()
    LONG_RECORDING   = auto()
    # STOPPING is transient (milliseconds); widget state = IDLE during it.
    # No dedicated enum value needed — widgets are set to IDLE enablement
    # before stop_recording() is called.


# ── HotkeyBridge ─────────────────────────────────────────────────────────────
class HotkeyBridge(QObject):
    """
    Threading bridge between the pynput OS keyboard thread and the Qt GUI thread.

    Owns the pynput Listener. Emits hotkey_pressed onto the Qt event queue so
    that ZERO widget calls happen on the pynput OS thread (Risk R08, R23, R25).

    The signal is connected to TranscriptionWindow.on_hotkey with
    Qt.ConnectionType.QueuedConnection — this is MANDATORY.

    Lifetime: constructed in TranscriptionWindow.__init__, started via start(),
    stopped via stop() from closeEvent. Qt parent is the TranscriptionWindow so
    Qt-side memory is reclaimed with the window. The listener itself is stopped
    explicitly via stop() because Qt parentage does NOT call Python stop() methods.
    """

    hotkey_pressed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ctrl_pressed: bool = False
        self._alt_pressed:  bool = False
        self._q_pressed:    bool = False
        self._listener: pynput_keyboard.Listener | None = None

    def start(self) -> None:
        """Create and start the pynput keyboard listener (daemon thread)."""
        self._listener = pynput_keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True   # OS reclaims thread on process exit
        self._listener.start()
        logger.info("pynput keyboard listener started")

    def stop(self) -> None:
        """Stop the pynput listener and wait up to 2 s for it to exit."""
        if self._listener is not None:
            self._listener.stop()
            self._listener.join(timeout=2.0)
            if self._listener.is_alive():
                logger.warning(
                    "pynput listener did not stop within 2 s; continuing shutdown"
                )

    def _on_press(self, key) -> None:
        """
        pynput callback — runs on the pynput OS thread.
        Updates modifier flags; emits hotkey_pressed when Ctrl+Alt+Q is held.
        MUST NOT touch any Qt widget directly.
        """
        try:
            if key in (pynput_keyboard.Key.ctrl,
                       pynput_keyboard.Key.ctrl_l,
                       pynput_keyboard.Key.ctrl_r):
                self._ctrl_pressed = True
            elif key in (pynput_keyboard.Key.alt,
                         pynput_keyboard.Key.alt_l,
                         pynput_keyboard.Key.alt_r):
                self._alt_pressed = True
            elif (hasattr(key, "char") and key.char == "q") or \
                 key == pynput_keyboard.KeyCode.from_char("q"):
                self._q_pressed = True

            if self._ctrl_pressed and self._alt_pressed and self._q_pressed:
                logger.info("Global hotkey Ctrl+Alt+Q detected")
                self.hotkey_pressed.emit()   # QueuedConnection → runs on GUI thread
                self._q_pressed = False      # single-fire reset: prevent key-repeat
        except (AttributeError, TypeError) as exc:
            logger.debug("Exception in _on_press: %s", exc)

    def _on_release(self, key) -> None:
        """
        pynput callback — runs on the pynput OS thread.
        Clears modifier flags. MUST NOT touch any Qt widget directly.
        """
        try:
            if key in (pynput_keyboard.Key.ctrl,
                       pynput_keyboard.Key.ctrl_l,
                       pynput_keyboard.Key.ctrl_r):
                self._ctrl_pressed = False
            elif key in (pynput_keyboard.Key.alt,
                         pynput_keyboard.Key.alt_l,
                         pynput_keyboard.Key.alt_r):
                self._alt_pressed = False
            elif (hasattr(key, "char") and key.char == "q") or \
                 key == pynput_keyboard.KeyCode.from_char("q"):
                self._q_pressed = False
        except (AttributeError, TypeError):
            pass


# ── Main window ───────────────────────────────────────────────────────────────
class TranscriptionWindow(QMainWindow):
    """
    The single application window.

    Owns all widgets, the state machine, timers, and coordinates with
    RealTimeTranscriber and ChimePlayer.

    Threading model:
      - All Qt widget access MUST happen on the GUI thread.
      - RealTimeTranscriber.record_loop runs on its own daemon thread and writes
        to transcriber.transcriptions / transcriber.audio_detected.
      - The GUI reads those attributes via a 30 ms QTimer (lock-free; one-tick
        staleness is acceptable per UX contract §6.3).
      - HotkeyBridge owns the pynput Listener (OS thread); its hotkey_pressed
        signal uses QueuedConnection so on_hotkey always runs on the GUI thread.
    """

    def __init__(self) -> None:
        super().__init__()

        # ── Window chrome ───────────────────────────────────────────────────
        # Set flags before show() — changing them after may hide/re-show the window.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_W, WINDOW_H)
        self.setMinimumSize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.setWindowOpacity(WINDOW_OPACITY)

        # Center on primary monitor
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width()  - WINDOW_W) // 2 + screen.left()
        y = (screen.height() - WINDOW_H) // 2 + screen.top()
        self.move(x, y)

        # ── Backend objects ──────────────────────────────────────────────────
        # Whisper model and transcriber are created lazily on first recording
        # start to keep the window-show fast (model load can take several seconds).
        self._device      = None   # set in _ensure_model_loaded()
        self._model       = None   # set in _ensure_model_loaded()
        self._transcriber = None   # set in _ensure_model_loaded()
        self._chime       = ChimePlayer()

        # ── State machine ────────────────────────────────────────────────────
        self._state = AppState.IDLE

        # ── Build UI ─────────────────────────────────────────────────────────
        self._build_ui()

        # ── Global hotkey bridge (Phase 4) ───────────────────────────────────
        # HotkeyBridge owns the pynput Listener and emits hotkey_pressed on the
        # pynput OS thread. QueuedConnection ensures on_hotkey runs on the GUI thread.
        self._hotkey_bridge = HotkeyBridge(parent=self)
        self._hotkey_bridge.hotkey_pressed.connect(
            self.on_hotkey,
            Qt.ConnectionType.QueuedConnection   # MANDATORY — Risk R08, R23
        )
        self._hotkey_bridge.start()

        # ── Poll timer (started only when recording is active) ───────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_tick)
        # Do NOT call start() here; started in _start_normal() / _start_long()

        # ── Spacebar shortcut (window-scoped, focus-independent) ─────────────
        # keyPressEvent alone doesn't fire reliably because QTextEdit (read-only)
        # still grabs keyboard focus and consumes Space. A window-scoped QShortcut
        # fires regardless of which child widget has focus.
        self._space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._space_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._space_shortcut.activated.connect(self._on_space_pressed)

    # ── Lazy model loader ──────────────────────────────────────────────────────
    def _ensure_model_loaded(self) -> None:
        """
        Load the Whisper model and create the transcriber on first call.
        Subsequent calls are no-ops. Called from _start_normal() / _start_long()
        so the window appears instantly and the model loads only when needed.
        """
        if self._transcriber is not None:
            return
        logger.info("Loading Whisper model '%s' ...", WHISPER_MODEL)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = whisper.load_model(WHISPER_MODEL, device=self._device)
        self._transcriber = RealTimeTranscriber(self._model)
        logger.info("Whisper model loaded on %s", self._device)

    # ── UI construction ────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        """Constructs all widgets, sets objectNames, wires click signals, assembles layouts."""

        # Central widget and main vertical layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)   # matches GTK set_border_width(10)
        main_layout.setSpacing(10)

        # ── Transcription text area ──────────────────────────────────────────
        self._text_area = QTextEdit()
        self._text_area.setObjectName("transcriptionView")
        self._text_area.setReadOnly(True)
        self._text_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        # Hide blinking caret (UX §2.1)
        self._text_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        # No explicit font — use system default (UX §2.1)
        main_layout.addWidget(self._text_area, stretch=1)

        # ── Audio activity indicator ─────────────────────────────────────────
        # Child of the text area's viewport so it overlays the text area.
        self._audio_indicator = QFrame(self._text_area.viewport())
        self._audio_indicator.setObjectName("audioIndicator")
        self._audio_indicator.setFixedSize(50, 4)
        self._audio_indicator.setVisible(False)
        self._reposition_indicator()

        # ── Button row ───────────────────────────────────────────────────────
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)
        main_layout.addWidget(btn_widget, stretch=0)   # fixed height, does not grow

        # Start button (left)
        self._start_btn = QPushButton("Start")
        self._start_btn.setObjectName("startButton")
        self._start_btn.setEnabled(True)
        # NoFocus prevents space from activating the focused button (UX §4.1)
        self._start_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._start_btn.clicked.connect(self._on_start_clicked)
        btn_layout.addWidget(self._start_btn, stretch=1)

        # Stop button (left, next to Start)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stopButton")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self._stop_btn, stretch=1)

        # Spacer between Stop and Long Record (mimics GTK pack_start / pack_end gap)
        btn_layout.addStretch(stretch=1)

        # Long Record button (right)
        self._long_btn = QPushButton("Long Record")
        self._long_btn.setObjectName("longButton")
        self._long_btn.setEnabled(True)
        self._long_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._long_btn.clicked.connect(self._on_long_clicked)
        btn_layout.addWidget(self._long_btn, stretch=1)

    # ── Indicator positioning ─────────────────────────────────────────────────
    def _reposition_indicator(self) -> None:
        """Keep audio indicator in top-right corner of the text area viewport."""
        vp = self._text_area.viewport()
        x = vp.width() - self._audio_indicator.width() - 5
        y = 5
        self._audio_indicator.move(max(0, x), y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_indicator()

    # ── State machine ─────────────────────────────────────────────────────────
    def _set_state(self, new_state: AppState) -> None:
        """
        Central transition. Enforces widget enablement per UX §3.4.
        Plays chime on entry to recording states or on return to IDLE.
        Must only be called from the GUI thread.
        """
        old_state = self._state
        self._state = new_state

        recording = new_state in (AppState.NORMAL_RECORDING, AppState.LONG_RECORDING)

        # Widget enablement (UX §3.4)
        self._start_btn.setEnabled(not recording)
        self._long_btn.setEnabled(not recording)
        self._stop_btn.setEnabled(recording)

        # Audio indicator: hide immediately when going idle
        if new_state == AppState.IDLE:
            self._audio_indicator.setVisible(False)

        # Chimes on state entry (UX §3.5)
        if new_state in (AppState.NORMAL_RECORDING, AppState.LONG_RECORDING):
            if old_state == AppState.IDLE:
                self._chime.play_start()
        elif new_state == AppState.IDLE:
            if old_state in (AppState.NORMAL_RECORDING, AppState.LONG_RECORDING):
                self._chime.play_end()

    # ── Action methods ────────────────────────────────────────────────────────
    def _start_normal(self) -> None:
        """Transition Idle → NormalRecording."""
        if self._state != AppState.IDLE:
            return   # guard against double-fire
        self._ensure_model_loaded()
        self._text_area.setPlainText("")
        self._transcriber.transcriptions = []
        self._set_state(AppState.NORMAL_RECORDING)   # plays start chime
        self._transcriber.start_recording(mode="normal")
        self._poll_timer.start()

    def _start_long(self) -> None:
        """Transition Idle → LongRecording."""
        if self._state != AppState.IDLE:
            return
        self._ensure_model_loaded()
        self._text_area.setPlainText("")
        self._transcriber.transcriptions = []
        self._set_state(AppState.LONG_RECORDING)   # plays start chime
        self._transcriber.start_recording(mode="long")
        self._poll_timer.start()

    def _stop_recording(self, from_hotkey: bool = False) -> None:
        """
        Transition any recording state → Idle.
        from_hotkey=True defers the clipboard write by HOTKEY_CLIPBOARD_DELAY_MS
        to avoid the modifier-release race (Risk R-arch-B).
        """
        if self._state == AppState.IDLE:
            return   # guard
        self._poll_timer.stop()
        self._set_state(AppState.IDLE)   # plays end chime, hides indicator
        self._transcriber.force_process_partial_frames()
        self._transcriber.stop_recording()

        final_text = "\n".join(self._transcriber.transcriptions)
        # Defer clipboard write when triggered by hotkey to avoid modifier-release race.
        # Button-driven stop writes immediately; hotkey-driven stop waits 150 ms.
        if from_hotkey:
            QTimer.singleShot(
                HOTKEY_CLIPBOARD_DELAY_MS,
                lambda: self._finalize_and_copy(final_text),
            )
        else:
            self._finalize_and_copy(final_text)

    def _finalize_and_copy(self, text: str) -> None:
        """Update text area with final text and write to clipboard. GUI thread only.

        Empty results (silence, aborted tap) are a no-op: they do not overwrite
        the text area or clipboard, so a previous successful transcription
        survives a subsequent short/silent tap.
        """
        if not text:
            logger.info("Empty transcription — preserving previous text/clipboard")
            return
        self._text_area.setPlainText(text)
        clip = QApplication.instance().clipboard()
        clip.setText(text)
        logger.info("Copied to clipboard: %.60s%s", text, "..." if len(text) > 60 else "")

    # ── Button slots ──────────────────────────────────────────────────────────
    def _on_start_clicked(self) -> None:
        self._start_normal()

    def _on_stop_clicked(self) -> None:
        self._stop_recording(from_hotkey=False)

    def _on_long_clicked(self) -> None:
        self._start_long()

    # ── Poll timer callback ───────────────────────────────────────────────────
    def _poll_tick(self) -> None:
        """Called every 30 ms while recording. Runs on GUI thread."""
        if self._state == AppState.LONG_RECORDING:
            self._text_area.setPlainText(LONG_MODE_PLACEHOLDER)
        elif self._state == AppState.NORMAL_RECORDING:
            current = "\n".join(self._transcriber.transcriptions)
            self._text_area.setPlainText(current)
        else:
            # State became IDLE between timer fire and this call — stop the timer.
            self._poll_timer.stop()
            return

        # Audio indicator: show/hide based on backend flag
        self._audio_indicator.setVisible(self._transcriber.audio_detected)
        self._reposition_indicator()

    # ── Keyboard handling ─────────────────────────────────────────────────────
    def _on_space_pressed(self) -> None:
        """
        Spacebar handler (wired via QShortcut, window-scoped).

        UX contract §4.1:
        - Space in Idle → NormalRecording
        - Space in NormalRecording → Idle
        - Space in LongRecording → ignored (no-op, no chime)
        """
        if self._state == AppState.IDLE:
            self._start_normal()
        elif self._state == AppState.NORMAL_RECORDING:
            self._stop_recording(from_hotkey=False)
        # LongRecording: intentional no-op per UX §4.1 / §3.3

    # ── Global hotkey slot ────────────────────────────────────────────────────
    def on_hotkey(self) -> None:
        """
        Slot connected to HotkeyBridge.hotkey_pressed (QueuedConnection).
        Runs on the GUI thread. Mirrors toggle_transcription() from gui-v0.8.py.

        UX §4.2 semantics:
        - Idle           → start NormalRecording + bring window forward
        - NormalRecording → stop
        - LongRecording  → NO-OP (confirmed in original toggle_transcription source)
        """
        if self._state == AppState.IDLE:
            # Bring window forward (UX §1.10)
            self.raise_()
            self.activateWindow()
            self._start_normal()
        elif self._state == AppState.NORMAL_RECORDING:
            self._stop_recording(from_hotkey=True)
        # LongRecording: intentional no-op (UX §3.3, §4.2)

    # ── Shutdown ──────────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        logger.info("closeEvent: beginning shutdown")

        # 1. Stop pynput listener (Risk R29)
        self._hotkey_bridge.stop()   # listener.stop() + join(timeout=2.0)

        # 2. Stop poll timer
        self._poll_timer.stop()

        # 3. Stop recording if active — do NOT copy to clipboard on shutdown (UX §6.4)
        if self._state != AppState.IDLE and self._transcriber is not None:
            try:
                self._transcriber.force_process_partial_frames()
            except Exception:
                pass
            try:
                self._transcriber.stop_recording()
            except Exception:
                pass
            self._state = AppState.IDLE

        # 4. Cleanup chime player (releases PyAudio stream)
        if hasattr(self, "_chime") and self._chime is not None:
            try:
                self._chime.cleanup()
            except Exception:
                pass

        # 5. Release GPU memory (Risk R30)
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

        # 6. Accept the close event → Qt destroys the window and exits event loop
        event.accept()
        QApplication.quit()


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    # Risk R15: chdir to src dir so relative path assumptions (if any) don't break.
    os.chdir(Path(__file__).parent)

    # Enable Ctrl+C from terminal to work (Risk R31).
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # DPI scaling — must be set BEFORE QApplication (Risk R21, R22).
    # Qt 6 enables high-DPI scaling by default; this sets the rounding policy.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("MyTranscribe")
    app.setStyleSheet(APP_QSS)

    logger.info("Starting MyTranscribe application")
    logger.info("Global hotkey Ctrl+Alt+Q enabled")

    window = TranscriptionWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

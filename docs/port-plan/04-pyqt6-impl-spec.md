# PyQt6 Implementation Specification — `src/gui_qt.py`

**Produced from:** `docs/port-plan/02-ux-contract.md` (source of truth), `docs/port-plan/01-architecture.md`,
`docs/port-plan/03-risk-verification.md`, `src/gui-v0.8.py` (reference only).

**Output file:** `src/gui_qt.py` — new file. `src/gui-v0.8.py` stays on disk as Linux reference.

**Branch:** `claude/windows-port-pyqt6`

> **Conflict flag**: The UX contract (§3.2) states that global hotkey fires on the **press** of Q while
> Ctrl+Alt are held. The architecture doc (§4 Risk A) says "signal is simpler — use that" for the
> pynput bridge. These are consistent; both are preserved here. No conflict with the meta-plan was found.

---

## 1. File Structure

Single file `src/gui_qt.py`. Top-level layout in read order:

```
1. Module docstring
2. stdlib imports
3. Third-party imports (PyQt6 first, then torch / whisper / pynput / project)
4. Logging setup
5. Constants block
6. APP_QSS triple-quoted string
7. class HotkeyBridge(QObject)
8. class TranscriptionWindow(QMainWindow)
9. def main()
10. if __name__ == "__main__": main()
```

### 1.1 Imports block

```python
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
from PyQt6.QtGui import QKeyEvent

import torch
import whisper
from pynput import keyboard as pynput_keyboard

# Project-local (resolve via __file__ to protect against cwd=System32, Risk R15)
_SRC_DIR = Path(__file__).parent
sys.path.insert(0, str(_SRC_DIR))
from transcriber_v12 import RealTimeTranscriber   # noqa: E402
from sound_utils import ChimePlayer               # noqa: E402
```

### 1.2 Logging setup

```python
# Set stdout to UTF-8 so non-ASCII transcripts don't crash the log (Risk R26)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gui_qt")
```

### 1.3 Constants block

```python
WINDOW_TITLE    = "Real-Time Transcription"
WINDOW_W        = 650
WINDOW_H        = 200
WINDOW_MIN_W    = 400
WINDOW_MIN_H    = 150
WINDOW_OPACITY  = 0.9
POLL_INTERVAL_MS = 30       # §6.2 — do not change to "save CPU"
HOTKEY_CLIPBOARD_DELAY_MS = 150  # Risk R09 / R-arch-B: delay clipboard write
                                  # when triggered by hotkey (modifiers still held)
WHISPER_MODEL   = "small"
LONG_MODE_PLACEHOLDER = "Recording in long mode..."
```

---

## 2. QSS Block

Full translation of the GTK CSS in `gui-v0.8.py` lines 24–52. Embed as a Python constant.
Colors are taken verbatim from UX contract §2 — no approximations.

```python
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
```

**Notes for the implementer:**
- `QPushButton#startButton` targets by `objectName`; set `self.start_btn.setObjectName("startButton")`.
- The `QFrame#audioIndicator` selector works because the indicator is a `QFrame`; its `objectName` must be `"audioIndicator"` (camelCase, no spaces).
- Qt on Windows renders the background-color only if `setAutoFillBackground(True)` is **not** needed — the stylesheet engine handles it. Do not call `setAutoFillBackground`.
- The disabled color `#99CC99` / `#CC9999` / `#9999CC` is a 50% lightened version of each base color; acceptable since UX contract says "greyed/inert", not a specific color.

---

## 3. Class Specifications

### 3.1 `HotkeyBridge(QObject)`

**Purpose:** Owns the `pynput` listener. Emits `hotkey_pressed` signal onto the Qt event queue so that zero widget calls happen on the pynput OS thread. This is the entire threading bridge for Risk R-arch-A / R08 / R23.

#### 3.1.1 `__init__`

```python
def __init__(self, parent: QObject | None = None) -> None:
```

Parameters:
- `parent` — standard Qt parent, pass the `TranscriptionWindow` so the bridge's lifetime is tied to the window.

Attributes set in `__init__`:

| Attribute | Type | Purpose |
|---|---|---|
| `_ctrl_pressed` | `bool` | Tracks whether Ctrl modifier is currently down |
| `_alt_pressed` | `bool` | Tracks whether Alt modifier is currently down |
| `_q_pressed` | `bool` | Single-fire gate: True only between Q-down and next Q-up |
| `_listener` | `pynput_keyboard.Listener` | The OS-level keyboard listener; created in `__init__`, started by `start()` |

#### 3.1.2 Signals

| Signal | Argument types | Emitted by | Connected to |
|---|---|---|---|
| `hotkey_pressed` | _(none)_ | `_on_press` (pynput OS thread) | `TranscriptionWindow.on_hotkey` via `Qt.ConnectionType.QueuedConnection` |

Declaration:
```python
hotkey_pressed = pyqtSignal()
```

`Qt.ConnectionType.QueuedConnection` is **mandatory** on this connection. The pynput callback runs on a foreign OS thread; without a queued connection, the slot would execute on that same foreign thread, mutating Qt widgets from outside the GUI thread, which causes undefined behavior (crash or silent data loss). See Risk R08, R23, R25.

#### 3.1.3 Methods

| Method | Signature | Role |
|---|---|---|
| `start` | `() -> None` | Creates `pynput_keyboard.Listener(on_press=self._on_press, on_release=self._on_release)`, stores as `self._listener`, calls `self._listener.start()` |
| `stop` | `() -> None` | Calls `self._listener.stop()` and `self._listener.join(timeout=2.0)` |
| `_on_press` | `(key) -> None` | pynput callback — updates modifier flags; if Ctrl+Alt+Q combo satisfied, emits `hotkey_pressed` and resets `_q_pressed`; no other actions |
| `_on_release` | `(key) -> None` | pynput callback — clears modifier flags and resets `_q_pressed` on Q-release |

**`_on_press` logic (exact):**

```python
def _on_press(self, key) -> None:
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
            self.hotkey_pressed.emit()   # queued → runs on GUI thread
            self._q_pressed = False      # single-fire reset
    except (AttributeError, TypeError) as exc:
        logger.debug("Exception in _on_press: %s", exc)
```

**`_on_release` logic (exact):**

```python
def _on_release(self, key) -> None:
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
```

---

### 3.2 `TranscriptionWindow(QMainWindow)`

**Purpose:** The single application window. Owns all widgets, state machine, timers, and coordinates with `HotkeyBridge`, `RealTimeTranscriber`, and `ChimePlayer`.

#### 3.2.1 `__init__`

```python
def __init__(self) -> None:
```

No parameters. Everything is self-contained.

**Order of operations in `__init__`:**

1. `super().__init__()`
2. Set window flags (always-on-top, native chrome)
3. Set window title, default size, minimum size, opacity
4. Center on primary screen
5. Apply QSS stylesheet
6. Create backend objects (`_device`, `_model`, `_transcriber`, `_chime`)
7. Set initial state (`_state = AppState.IDLE`)
8. Build UI (`_build_ui()`)
9. Create and wire `HotkeyBridge`
10. Create poll timer (but do NOT start it yet)
11. Connect signals
12. `show()`

#### 3.2.2 Attributes

| Attribute | Type | Purpose |
|---|---|---|
| `_state` | `AppState` | Current state machine state |
| `_device` | `str` | `"cuda"` or `"cpu"` |
| `_model` | `whisper.Whisper` | Loaded Whisper model |
| `_transcriber` | `RealTimeTranscriber` | Backend transcription engine |
| `_chime` | `ChimePlayer` | Chime sound player |
| `_hotkey_bridge` | `HotkeyBridge` | pynput bridge |
| `_poll_timer` | `QTimer` | 30 ms GUI update timer; not started until recording begins |
| `_text_area` | `QTextEdit` | Transcription display |
| `_audio_indicator` | `QFrame` | Audio activity indicator |
| `_start_btn` | `QPushButton` | Start button |
| `_stop_btn` | `QPushButton` | Stop button |
| `_long_btn` | `QPushButton` | Long Record button |

#### 3.2.3 Signals declared on this class

| Signal | Argument types | Emitted by | Connected to |
|---|---|---|---|
| _(none declared)_ | — | — | — |

`TranscriptionWindow` does not declare signals; it receives signals. All internal communication from background threads arrives via `HotkeyBridge.hotkey_pressed` (queued). The Whisper worker communicates only through `_transcriber.transcriptions` and `_transcriber.audio_detected` (lock-free shared state read by the 30 ms timer on the GUI thread).

#### 3.2.4 Methods

| Method | Signature | Role |
|---|---|---|
| `_build_ui` | `() -> None` | Constructs all widgets, sets objectNames, wires click signals, assembles layouts |
| `_set_state` | `(new_state: AppState) -> None` | Central state-machine transition: enables/disables widgets, shows/hides indicator, plays chime on entry |
| `_on_start_clicked` | `() -> None` | Slot for Start button `clicked`; calls `_start_normal()` |
| `_on_stop_clicked` | `() -> None` | Slot for Stop button `clicked`; calls `_stop_recording()` |
| `_on_long_clicked` | `() -> None` | Slot for Long Record button `clicked`; calls `_start_long()` |
| `_start_normal` | `() -> None` | Transitions Idle → NormalRecording |
| `_start_long` | `() -> None` | Transitions Idle → LongRecording |
| `_stop_recording` | `(from_hotkey: bool = False) -> None` | Transitions any recording state → Idle; `from_hotkey` defers clipboard write by `HOTKEY_CLIPBOARD_DELAY_MS` |
| `_poll_tick` | `() -> None` | Called by `_poll_timer` every 30 ms; updates text area and audio indicator |
| `_finalize_and_copy` | `(text: str) -> None` | Updates text area with final text, then sets clipboard; must run on GUI thread |
| `on_hotkey` | `() -> None` | Slot connected to `HotkeyBridge.hotkey_pressed`; implements toggle logic matching `toggle_transcription` from GTK source |
| `keyPressEvent` | `(event: QKeyEvent) -> None` | Override; handles Spacebar per §4.1; all other keys fall through to super |
| `closeEvent` | `(event) -> None` | Override; performs full shutdown sequence (§11) |

---

## 4. State Machine Implementation

### 4.1 Enum definition

```python
class AppState(Enum):
    IDLE             = auto()
    NORMAL_RECORDING = auto()
    LONG_RECORDING   = auto()
    # STOPPING is transient (milliseconds); widget state = IDLE during it.
    # No dedicated enum value needed — widgets are set to IDLE enablement
    # before stop_recording() is called.
```

### 4.2 Allowed transitions (Python dict comment for reference)

```python
# TRANSITION_TABLE = {
#   (AppState.IDLE,             "start_normal")  -> AppState.NORMAL_RECORDING,
#   (AppState.IDLE,             "start_long")    -> AppState.LONG_RECORDING,
#   (AppState.IDLE,             "hotkey")        -> AppState.NORMAL_RECORDING,
#   (AppState.IDLE,             "space")         -> AppState.NORMAL_RECORDING,
#   (AppState.NORMAL_RECORDING, "stop")          -> AppState.IDLE,
#   (AppState.NORMAL_RECORDING, "hotkey")        -> AppState.IDLE,
#   (AppState.NORMAL_RECORDING, "space")         -> AppState.IDLE,
#   (AppState.LONG_RECORDING,   "stop")          -> AppState.IDLE,
#   (AppState.LONG_RECORDING,   "hotkey")        -> AppState.IDLE,  # NO-OP (see §3.3)
#   (AppState.LONG_RECORDING,   "space")         -> AppState.IDLE,  # NO-OP (see §3.3)
# }
#
# DISALLOWED (must be early-returned or ignored):
#   (AppState.LONG_RECORDING,  "space")   -> no-op (UX §4.1)
#   (AppState.LONG_RECORDING,  "hotkey")  -> no-op (UX §3.3, §4.2)
#   (ANY_RECORDING,            "start_*") -> no-op (buttons disabled + guard)
#   (AppState.IDLE,            "stop")    -> no-op (button disabled + guard)
```

### 4.3 `_set_state` implementation

```python
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
```

**Important:** `_chime.play_start()` and `_chime.play_end()` return immediately (ChimePlayer runs its own thread); this method does NOT block. Do not add `time.sleep` here.

---

## 5. Widget-by-widget Build Recipe

All construction happens inside `_build_ui()`. Call this from `__init__` after backend objects are created.

### 5.1 Window flags and properties

```python
# Set BEFORE show() — changing flags after show() may hide and re-show the window
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
```

### 5.2 Central widget and main layout

```python
central = QWidget()
self.setCentralWidget(central)
main_layout = QVBoxLayout(central)
main_layout.setContentsMargins(10, 10, 10, 10)   # matches GTK set_border_width(10)
main_layout.setSpacing(10)
```

### 5.3 Transcription text area

| Property | Value |
|---|---|
| PyQt6 class | `QTextEdit` |
| Variable | `self._text_area` |
| objectName | `"transcriptionView"` |
| Construction | `self._text_area = QTextEdit()` |
| `setReadOnly` | `True` |
| `setLineWrapMode` | `QTextEdit.LineWrapMode.WidgetWidth` |
| Cursor | `viewport().setCursor(Qt.CursorShape.ArrowCursor)` (hides blinking caret) |
| SizePolicy | `Expanding, Expanding` — grows to fill all space above button row |
| Added to layout | `main_layout.addWidget(self._text_area, stretch=1)` |

```python
self._text_area = QTextEdit()
self._text_area.setObjectName("transcriptionView")
self._text_area.setReadOnly(True)
self._text_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
self._text_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
# No explicit font — use system default (UX §2.1)
main_layout.addWidget(self._text_area, stretch=1)
```

### 5.4 Audio activity indicator

The indicator overlays the top-right corner of the text area. In PyQt6 the cleanest approach is a child `QFrame` of the text area's viewport, manually positioned.

| Property | Value |
|---|---|
| PyQt6 class | `QFrame` |
| Variable | `self._audio_indicator` |
| objectName | `"audioIndicator"` |
| Fixed size | `50 x 4` logical px (matches GTK `set_size_request(50, 4)`) |
| Initial visibility | Hidden (`setVisible(False)`) |
| Parent | `self._text_area.viewport()` |

```python
self._audio_indicator = QFrame(self._text_area.viewport())
self._audio_indicator.setObjectName("audioIndicator")
self._audio_indicator.setFixedSize(50, 4)
self._audio_indicator.setVisible(False)
# Position: 5 px from top, 5 px from right of the viewport
# Actual placement is done in _reposition_indicator(), called on resize
self._reposition_indicator()
```

```python
def _reposition_indicator(self) -> None:
    """Keep indicator in top-right corner of the text area viewport."""
    vp = self._text_area.viewport()
    x = vp.width()  - self._audio_indicator.width()  - 5
    y = 5
    self._audio_indicator.move(max(0, x), y)
```

Override `resizeEvent` on `TranscriptionWindow` to call `_reposition_indicator()` after `super().resizeEvent(event)`.

**Note on DPI (Risk R22):** `setFixedSize(50, 4)` uses logical pixels. On a 150% DPI screen, Qt will render 75 physical pixels wide × 6 physical pixels tall, which remains visible. If the user reports invisibility at 200% DPI, replace `setFixedSize(50, 4)` with `setFixedSize(50, max(4, self.fontMetrics().height() // 4))`.

### 5.5 Button row

| Property | Value |
|---|---|
| Container | `QHBoxLayout` inside a `QWidget` |
| Spacing | `10` px |

```python
btn_widget = QWidget()
btn_layout = QHBoxLayout(btn_widget)
btn_layout.setContentsMargins(0, 0, 0, 0)
btn_layout.setSpacing(10)
main_layout.addWidget(btn_widget, stretch=0)   # fixed height, does not grow
```

#### 5.5.1 Start button

```python
self._start_btn = QPushButton("Start")
self._start_btn.setObjectName("startButton")
self._start_btn.setEnabled(True)
# Prevent space-bar from activating the focused button (UX §4.1 note)
self._start_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
self._start_btn.clicked.connect(self._on_start_clicked)
btn_layout.addWidget(self._start_btn, stretch=1)
```

#### 5.5.2 Stop button

```python
self._stop_btn = QPushButton("Stop")
self._stop_btn.setObjectName("stopButton")
self._stop_btn.setEnabled(False)
self._stop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
self._stop_btn.clicked.connect(self._on_stop_clicked)
btn_layout.addWidget(self._stop_btn, stretch=1)
```

#### 5.5.3 Spacer between Stop and Long Record

```python
btn_layout.addStretch(stretch=1)   # mimics GTK pack_start / pack_end gap
```

#### 5.5.4 Long Record button

```python
self._long_btn = QPushButton("Long Record")
self._long_btn.setObjectName("longButton")
self._long_btn.setEnabled(True)
self._long_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
self._long_btn.clicked.connect(self._on_long_clicked)
btn_layout.addWidget(self._long_btn, stretch=1)
```

**Focus policy note (UX §4.1):** `Qt.FocusPolicy.NoFocus` on all buttons means Tab and mouse-click do not give a button keyboard focus. This prevents spacebar from activating a focused button separately from the window-level `keyPressEvent`. The text area (`QTextEdit`) is read-only and will not consume space. The window itself (`QMainWindow`) receives key events through `keyPressEvent`.

---

## 6. Threading Bridge Design

### 6.1 Signal/slot routing diagram

```
┌────────────────────────────────────────────────────────────────────┐
│  pynput OS thread                                                  │
│  HotkeyBridge._on_press()                                          │
│      │                                                             │
│      │  hotkey_pressed.emit()  [pyqtSignal — no args]             │
│      │  (returns immediately; Qt queues the event)                 │
└──────┼─────────────────────────────────────────────────────────────┘
       │  [Qt event queue — QueuedConnection]
       ▼
┌────────────────────────────────────────────────────────────────────┐
│  GUI thread (Qt event loop)                                        │
│  TranscriptionWindow.on_hotkey()                                   │
│      ├─► toggle state machine                                      │
│      ├─► call _start_normal() / _stop_recording()                  │
│      └─► update widgets (safe — GUI thread)                        │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Whisper/PyAudio worker thread (RealTimeTranscriber.record_loop)   │
│      ├─► appends to transcriber.transcriptions  [plain list]       │
│      └─► sets transcriber.audio_detected        [plain bool]       │
└──────────────────────────────────────────────────────────────────- ┘
       │  read by GUI thread only, via 30 ms QTimer
       ▼
┌────────────────────────────────────────────────────────────────────┐
│  GUI thread                                                        │
│  TranscriptionWindow._poll_tick()  [called by QTimer every 30 ms]  │
│      ├─► read transcriber.transcriptions → _text_area.setPlainText │
│      └─► read transcriber.audio_detected → _audio_indicator.show/hide│
└────────────────────────────────────────────────────────────────────┘
```

### 6.2 Connection setup (in `__init__`)

```python
self._hotkey_bridge = HotkeyBridge(parent=self)
self._hotkey_bridge.hotkey_pressed.connect(
    self.on_hotkey,
    Qt.ConnectionType.QueuedConnection   # MANDATORY — see Risk R08, R23
)
self._hotkey_bridge.start()
```

### 6.3 `_poll_timer` setup

```python
self._poll_timer = QTimer(self)
self._poll_timer.setInterval(POLL_INTERVAL_MS)   # 30 ms
self._poll_timer.timeout.connect(self._poll_tick)
# Do NOT call start() here — started in _start_normal() / _start_long()
```

### 6.4 Whisper worker thread

The `RealTimeTranscriber.record_loop` is a plain `threading.Thread` (daemon) started by `transcriber.start_recording(mode=...)`. The GUI never calls methods on this thread directly. Communication is one-directional via the shared `transcriptions` list and `audio_detected` bool, read lock-free on the GUI thread every 30 ms.

**Warning:** Never call `QApplication.instance().clipboard().setText(...)` from `record_loop` or any thread other than the GUI thread. Doing so may crash or silently lose the clipboard content (Risk R08). The clipboard write is always invoked from `_finalize_and_copy`, which is only ever called from the GUI thread (via `_stop_recording` which is only reachable from button slots, `keyPressEvent`, `on_hotkey`, and `closeEvent` — all GUI-thread code paths).

---

## 7. State Machine — Action Methods

### 7.1 `_start_normal()`

```python
def _start_normal(self) -> None:
    if self._state != AppState.IDLE:
        return   # guard against double-fire
    self._text_area.setPlainText("")
    self._transcriber.transcriptions = []
    self._set_state(AppState.NORMAL_RECORDING)   # plays start chime
    self._transcriber.start_recording(mode="normal")
    self._poll_timer.start()
```

### 7.2 `_start_long()`

```python
def _start_long(self) -> None:
    if self._state != AppState.IDLE:
        return
    self._text_area.setPlainText("")
    self._transcriber.transcriptions = []
    self._set_state(AppState.LONG_RECORDING)   # plays start chime
    self._transcriber.start_recording(mode="long")
    self._poll_timer.start()
```

### 7.3 `_stop_recording(from_hotkey: bool = False)`

```python
def _stop_recording(self, from_hotkey: bool = False) -> None:
    if self._state == AppState.IDLE:
        return   # guard
    self._poll_timer.stop()
    self._set_state(AppState.IDLE)   # plays end chime, hides indicator
    self._transcriber.force_process_partial_frames()
    self._transcriber.stop_recording()

    final_text = "\n".join(self._transcriber.transcriptions)
    # Defer clipboard write when triggered by hotkey to avoid modifier-release race
    # (Risk R-arch-B, architecture doc §4 Risk B).
    # Button-driven stop writes immediately; hotkey-driven stop waits 150 ms.
    if from_hotkey:
        QTimer.singleShot(
            HOTKEY_CLIPBOARD_DELAY_MS,
            lambda: self._finalize_and_copy(final_text),
        )
    else:
        self._finalize_and_copy(final_text)
```

### 7.4 `_finalize_and_copy(text: str)`

```python
def _finalize_and_copy(self, text: str) -> None:
    """Must only be called from the GUI thread."""
    self._text_area.setPlainText(text)
    clip = QApplication.instance().clipboard()
    clip.setText(text)
    logger.info("Copied to clipboard: %.60s%s", text, "..." if len(text) > 60 else "")
```

**Clipboard contract notes (UX §5.6 / Risk R09):**
- `clip.setText(text)` on Windows writes `CF_UNICODETEXT` synchronously. No `.store()` call is needed — Windows clipboard persists after `QApplication` exits (the OS maintains the clipboard independently of the owning process).
- To force materialization before a fast paste (Risk R09), reading `clip.text()` immediately after `setText` is sufficient; however the `HOTKEY_CLIPBOARD_DELAY_MS = 150` deferral already handles this by giving enough time before the user can press Ctrl+V.
- **Never** call `clip.setText()` from a non-GUI thread. This constraint is enforced architecturally: `_finalize_and_copy` is reachable only from `_stop_recording`, which is only called from GUI-thread code paths.

---

## 8. Poll Timer Callback

```python
def _poll_tick(self) -> None:
    """Called every 30 ms while recording. Runs on GUI thread."""
    if self._state == AppState.LONG_RECORDING:
        self._text_area.setPlainText(LONG_MODE_PLACEHOLDER)
    elif self._state == AppState.NORMAL_RECORDING:
        current = "\n".join(self._transcriber.transcriptions)
        self._text_area.setPlainText(current)
    else:
        # State became IDLE between timer fire and this call — stop the timer
        self._poll_timer.stop()
        return

    # Audio indicator: show/hide based on backend flag
    self._audio_indicator.setVisible(self._transcriber.audio_detected)
    self._reposition_indicator()
```

**Note:** `_set_state(IDLE)` calls `self._poll_timer.stop()` via `_stop_recording`, so the timer will not fire after the state is IDLE in the normal path. The `else` branch is a defensive catch for any edge case where a timer tick races a state change.

---

## 9. Keyboard Handling

```python
def keyPressEvent(self, event: QKeyEvent) -> None:
    """
    Window-level key handler. Intercepts Space before any child widget sees it.
    All other keys fall through to super().keyPressEvent(event).

    UX contract §4.1:
    - Space in Idle → NormalRecording
    - Space in NormalRecording → Idle
    - Space in LongRecording → ignored (no-op, no chime)
    """
    if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
        if self._state == AppState.IDLE:
            self._start_normal()
            return   # consumed
        elif self._state == AppState.NORMAL_RECORDING:
            self._stop_recording(from_hotkey=False)
            return   # consumed
        # LongRecording: fall through silently (ignored per UX §4.1 / §3.3)
        return

    # All other keys pass through — lets Alt+F4, Win, etc. work normally (UX §4.3)
    super().keyPressEvent(event)
```

**Why `not event.isAutoRepeat()`:** Without this guard, holding Space down would trigger multiple state transitions. Checking `isAutoRepeat()` ensures only the first physical keydown fires.

**Why window-level (not button-level):** If buttons had focus, Qt would send Space to the focused button before `keyPressEvent` sees it. All three buttons have `setFocusPolicy(Qt.FocusPolicy.NoFocus)` (§5.5), which means the window receives Space directly. This is equivalent to GTK's window-level `key-press-event` connection in `gui-v0.8.py:233`.

---

## 10. Global Hotkey Integration

### 10.1 `on_hotkey` slot

```python
def on_hotkey(self) -> None:
    """
    Slot connected to HotkeyBridge.hotkey_pressed (QueuedConnection).
    Runs on the GUI thread. Mirrors toggle_transcription() from gui-v0.8.py.

    UX §4.2 semantics:
    - Idle           → start NormalRecording + bring window forward
    - NormalRecording → stop
    - LongRecording  → NO-OP (confirmed by reading toggle_transcription source)
    """
    if self._state == AppState.IDLE:
        # Bring window forward (UX §1.10)
        self.raise_()
        self.activateWindow()
        self._start_normal()
    elif self._state == AppState.NORMAL_RECORDING:
        self._stop_recording(from_hotkey=True)
    # LongRecording: intentional no-op
```

### 10.2 Window-raise behavior (UX §1.10)

`self.raise_()` brings the Qt window to the front of the z-order. `self.activateWindow()` requests keyboard focus. On Windows, `activateWindow()` may silently fail if the foreground lock is held by another elevated process (Risk R05). This is acceptable per the UX contract — the chime confirms recording started even if the window does not steal focus in every case.

### 10.3 pynput Listener ownership

The `pynput` Listener is created and owned by `HotkeyBridge`, which is owned by `TranscriptionWindow` (passed as `parent=self`). The Listener starts in `HotkeyBridge.start()` called from `TranscriptionWindow.__init__`. The Listener is stopped in `HotkeyBridge.stop()` called from `TranscriptionWindow.closeEvent`. No global variable holds the Listener; its lifetime is bounded by the window's lifetime.

---

## 11. Event Loop Integration

### 11.1 `main()` function

```python
def main() -> None:
    # Risk R15: chdir to src dir so relative path assumptions (if any) don't break
    os.chdir(Path(__file__).parent)

    # Enable Ctrl+C from terminal to work (Risk R31)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # DPI scaling — must be set BEFORE QApplication (Risk R21, R22)
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
```

**Note:** `QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)` was the Qt 5 API; in Qt 6, high-DPI scaling is on by default and `setHighDpiScaleFactorRoundingPolicy` is the correct override point.

### 11.2 `QTimer` replacing `GLib.timeout_add`

| GTK original | PyQt6 equivalent |
|---|---|
| `GLib.timeout_add(30, self.update_transcription_callback)` | `self._poll_timer.start()` where `_poll_timer.setInterval(30)` and `timeout.connect(self._poll_tick)` |
| Return `True` to repeat | Timer repeats by default; call `.stop()` to halt |
| Return `False` to stop | Call `self._poll_timer.stop()` from inside the slot |
| `GLib.source_remove(id)` | `self._poll_timer.stop()` |

### 11.3 `QTimer.singleShot` replacing `GLib.idle_add`

| GTK original | PyQt6 equivalent |
|---|---|
| `GLib.idle_add(fn)` | `QTimer.singleShot(0, fn)` |
| `GLib.idle_add(self.text_buffer.set_text, text)` | `QTimer.singleShot(0, lambda: self._text_area.setPlainText(text))` |

In `_stop_recording`, the clipboard deferral uses `QTimer.singleShot(HOTKEY_CLIPBOARD_DELAY_MS, ...)` rather than `0`. The `GLib.idle_add` in the original GTK code (`stop_transcription:290`) is replaced by a direct call to `_finalize_and_copy` in the non-hotkey path (no marshaling needed because we're already on the GUI thread).

### 11.4 Whisper background thread

```python
# No change from the GTK version: RealTimeTranscriber owns its own threading.Thread.
# Do not introduce QThread. Plain threading.Thread works correctly as long as
# all Qt widget interactions are marshaled via signals (which they are).
```

---

## 12. Exit Paths

All three exit paths (window close, Ctrl+C, Ctrl+Alt+Q then close) must converge on `closeEvent`.

### 12.1 `closeEvent`

```python
def closeEvent(self, event) -> None:
    logger.info("closeEvent: beginning shutdown")

    # 1. Stop pynput listener (Risk R29)
    self._hotkey_bridge.stop()   # calls listener.stop() + listener.join(timeout=2.0)

    # 2. Stop poll timer
    self._poll_timer.stop()

    # 3. Stop recording if active — do NOT copy to clipboard on shutdown (UX §6.4)
    if self._state != AppState.IDLE:
        self._transcriber.force_process_partial_frames()
        self._transcriber.stop_recording()
        self._state = AppState.IDLE

    # 4. Cleanup chime player (releases PyAudio stream)
    if hasattr(self, "_chime"):
        self._chime.cleanup()

    # 5. Release GPU memory (Risk R30)
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass

    # 6. Accept the close event → Qt destroys the window and exits event loop
    event.accept()
    QApplication.quit()
```

### 12.2 Ctrl+C from terminal

`signal.signal(signal.SIGINT, signal.SIG_DFL)` in `main()` causes Python to raise `KeyboardInterrupt` on the next Python bytecode instruction after the signal arrives. Qt on Windows does not deliver SIGINT to the event loop by default; `SIG_DFL` bypasses Qt and terminates via the Python runtime. `closeEvent` is **not** guaranteed to run on SIGINT with `SIG_DFL`. This is acceptable per architecture doc §5 Risk A:

> "Fallback to `os._exit(0)` if the listener thread won't die."

For a cleaner SIGINT path (optional, not required for Phase 3), a `QTimer` firing every 200 ms that calls `app.processEvents()` lets Python check for pending signals. This can be added in Phase 5 if the user reports SIGINT leaves zombie threads.

### 12.3 Ctrl+Alt+Q when Idle

Per UX §3.2, Ctrl+Alt+Q in Idle starts recording. It does **not** exit the app. If the user wants to exit, they close the window. No "third press to quit" behavior is added.

### 12.4 Listener stop robustness

In `HotkeyBridge.stop()`:

```python
def stop(self) -> None:
    self._listener.stop()
    self._listener.join(timeout=2.0)
    if self._listener.is_alive():
        logger.warning("pynput listener did not stop within 2 s; continuing shutdown")
        # Do not os._exit here — let Qt handle the exit normally;
        # the daemon thread will be killed when the process exits.
```

The `pynput` listener thread is started as a non-daemon thread by default. If `join(timeout=2.0)` times out, the process may hang. To avoid this, either:
- Set `self._listener.daemon = True` before `self._listener.start()` — the OS reclaims the thread on process exit.
- Or call `os._exit(0)` after the timeout if the process is already in `closeEvent`.

**Recommendation:** Set `daemon=True` on the listener thread. Add this to `HotkeyBridge.start()`:

```python
def start(self) -> None:
    self._listener = pynput_keyboard.Listener(
        on_press=self._on_press,
        on_release=self._on_release,
    )
    self._listener.daemon = True
    self._listener.start()
```

---

## 13. Things NOT to Do

The implementing agent must not add or change the following:

1. **No custom title bar.** Do not replicate `Gtk.HeaderBar`. Use native Windows chrome (`QMainWindow` default). The title must still read "Real-Time Transcription". (UX §1.11, §1.12, §7.1)

2. **No QML.** Do not introduce `PyQt6.QtQuick`, `QQmlEngine`, or any `.qml` files. Keep the dependency surface to `PyQt6.QtWidgets` + `PyQt6.QtCore` + `PyQt6.QtGui` only.

3. **No `QThread`.** Keep `RealTimeTranscriber`'s plain `threading.Thread`. Introducing `QThread` would require wrapping the transcriber, which touches `transcriber_v12.py` — out of scope for Phase 3 (architecture §2, constraint "Phase 3 does not modify `transcriber_v12.py`").

4. **No `QtConcurrent`.** Same rationale.

5. **No silent Whisper exception swallowing.** The `transcriber_v12.py` already catches errors and inserts `"[Transcription Error: ...]"` strings into `self.transcriptions`. The GUI's `_poll_tick` will display those naturally via `_text_area.setPlainText(current)`. Do not add a separate `try/except` around the widget update that hides transcription error strings.

6. **No progress bar, tray icon, toast, or status bar.** (UX §2.7)

7. **No menu bar.** The default `QMainWindow` creates a `QMenuBar`; call `self.menuBar().setVisible(False)` or simply do not add any menus. (UX §2.7)

8. **No `time.sleep` on the GUI thread.** All delays go through `QTimer.singleShot`. (UX §6.5)

9. **No `clipboard().store()` call.** Not needed on Windows (UX §5.6). Adding it would be a no-op but signals misunderstanding of the contract.

10. **No auto-stop detection for long mode.** The GUI must not watch for the backend's 180 s auto-stop and auto-transition. The user must still click Stop. (UX §3.2, the contract note on `LongRecording → Backend auto-timeout`.) Risk R36 proposes wiring `recording_finished` signal from the transcriber — that is a Phase 4+ enhancement; do not add it in Phase 3.

---

## 14. Annotated Signal/Slot Table

```
Signal                        | Emitter thread  | Receiver            | Connection type
------------------------------|-----------------|---------------------|------------------
HotkeyBridge.hotkey_pressed   | pynput OS thread| TranscriptionWindow | QueuedConnection  ← MANDATORY
QTimer.timeout (poll)         | GUI thread      | _poll_tick          | AutoConnection (same thread)
QPushButton.clicked (start)   | GUI thread      | _on_start_clicked   | AutoConnection
QPushButton.clicked (stop)    | GUI thread      | _on_stop_clicked    | AutoConnection
QPushButton.clicked (long)    | GUI thread      | _on_long_clicked    | AutoConnection
QTimer.singleShot (clipboard) | GUI thread      | _finalize_and_copy  | lambda / direct call
```

---

## 15. Conflict and Risk Flags

### Flag 1 — `recording_finished` signal (Risk R36 vs Phase 3 scope)

`03-risk-verification.md` Risk R36 proposes: "RealTimeTranscriber emits `recording_finished = pyqtSignal()` when `record_loop` exits naturally; slot on main thread calls `update_button_states()`."

**This is NOT in scope for Phase 3.** The UX contract §3.2 explicitly says the GUI must NOT auto-stop on the 180 s backend timer. Wiring `recording_finished` is a Phase 4+ enhancement. Do not add it in `gui_qt.py` Phase 3. If added later, the signal must go through `QueuedConnection` and must NOT trigger the clipboard copy path (only user-initiated stops copy to clipboard per UX §5.1, §6.4).

### Flag 2 — `HotkeyBridge` parentage vs lifetime

`HotkeyBridge.__init__(parent=self)` sets the Qt parent to the window. Qt does NOT automatically call Python methods like `stop()` on child objects when the parent is destroyed — it only frees Qt-side memory. The `closeEvent` must explicitly call `self._hotkey_bridge.stop()`. Do not assume Qt parentage means "stop the listener on window close".

### Flag 3 — `QApplication.exec()` return in `main()`

`sys.exit(app.exec())` is correct for PyQt6. In some Windows environments, `app.exec()` returns a non-zero exit code when the process is terminated by signal rather than by `QApplication.quit()`. This is normal; `sys.exit` converts it to the process exit code. Do not add logic to suppress non-zero exit codes.

### Flag 4 — Architecture doc §4 Risk B vs UX contract §5 on clipboard timing

Architecture doc recommends `QTimer.singleShot(150, ...)` for the hotkey-driven clipboard write. UX contract §5.1 says "exactly once per recording session, at the moment recording stops". These are compatible: the 150 ms delay is sub-perceptual and the write still happens before the user can press Ctrl+V. The implementation uses `from_hotkey` parameter to select the deferred vs immediate path. This flag is informational — no conflict, both documents can be satisfied simultaneously.

### Flag 5 — `menuBar().setVisible(False)` vs default QMainWindow behavior

`QMainWindow` does not create a visible menu bar unless `menuBar()` is called or a menu is added. In PyQt6, calling `self.menuBar()` creates the bar lazily. Do not call `menuBar()` anywhere in `_build_ui()` and no menu bar will appear. No explicit `setVisible(False)` is required.

---

## 16. Implementation Checklist

The following must all be true before Phase 3 is marked complete (maps to architecture doc §3 exit criteria):

- [ ] `python src/gui_qt.py` opens a 650×200 window, title "Real-Time Transcription", always on top, 0.9 opacity
- [ ] Start button (#00FF00), Stop button (#FF0000), Long Record button (#0000FF) rendered with correct colors
- [ ] Start/Long enabled at startup; Stop disabled
- [ ] Clicking Start plays start chime, calls `transcriber.start_recording("normal")`, disables Start/Long, enables Stop
- [ ] Clicking Long plays start chime, calls `transcriber.start_recording("long")`, shows placeholder text
- [ ] Clicking Stop plays end chime, calls `force_process_partial_frames()` + `stop_recording()`, re-enables Start/Long
- [ ] Final transcription text appears in text area and is on the Windows clipboard after Stop
- [ ] Ctrl+V in Notepad pastes the transcript
- [ ] Spacebar toggles normal recording when window has focus; ignored in long mode
- [ ] `pynput` hotkey is wired (Phase 4); in Phase 3, `HotkeyBridge` is constructed and `on_hotkey` is implemented and tested via a button-click surrogate
- [ ] Audio indicator appears/disappears at ~30 ms cadence when `transcriber.audio_detected` changes
- [ ] Audio indicator positioned at top-right of text area, 50×4 px, dark green
- [ ] Closing the window exits the process cleanly; no zombie threads; mic re-usable immediately
- [ ] No `QTextEdit` or `QClipboard` calls from any non-GUI thread (verify by code inspection / T21)
- [ ] Non-ASCII text (café, résumé) does not cause `UnicodeEncodeError` in the terminal log

---

*Spec line count target: approximately 450–550 lines of Markdown. QSS block: approximately 1,700 bytes.*

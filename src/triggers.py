"""
triggers.py — extra global start/stop triggers for gui_med.py.

Besides Ctrl+Alt+Q (gui_qt.HotkeyBridge), dictation can be started/stopped with:

  * a single key (default F9, hold to talk)
  * a mouse button (default the "forward" thumb button, toggle)

Each has its own mode: "hold" (record while held) or "toggle" (press to
start, press again to stop). Chosen in the Options screen (settings.py).

On Windows the trigger key/button press is swallowed so the app with focus
(the EMR) never sees it: F9 means "update field" in Word, and the thumb
buttons navigate back/forward in browsers. The back button (x1) is not the
default because, if suppression ever failed, it could navigate a web EMR away
from an unsaved note.

Threading: pynput delivers events on its own OS threads. This class only emits
Qt signals; connect them with Qt.QueuedConnection so slots run on the GUI
thread. Hook callbacks must stay tiny or Windows lags all keyboard/mouse input.
"""

import logging
import sys
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("triggers")

# Windows virtual-key codes for the keys we allow as a single-key trigger.
KEY_CHOICES = {f"f{n}": 0x6F + n for n in range(1, 13)}       # F1 = 0x70 ... F12 = 0x7B
KEY_CHOICES.update({"pause": 0x13, "scroll_lock": 0x91})
MOUSE_CHOICES = {"x2": "Mouse forward button", "x1": "Mouse back button", "middle": "Middle mouse button"}

_WM_KEYDOWN, _WM_KEYUP, _WM_SYSKEYDOWN, _WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
_WM_MBUTTONDOWN, _WM_MBUTTONUP = 0x0207, 0x0208
_WM_XBUTTONDOWN, _WM_XBUTTONUP = 0x020B, 0x020C
_XBUTTON = {"x1": 1, "x2": 2}


def key_label(key: Optional[str]) -> str:
    if not key:
        return "None"
    return key.replace("_", " ").title() if len(key) > 3 else key.upper()


@dataclass
class TriggerConfig:
    key: Optional[str] = "f9"          # None = no single-key trigger
    key_hold: bool = True              # F9: hold to talk
    mouse: Optional[str] = "x2"        # None = no mouse trigger
    mouse_hold: bool = False           # mouse button: toggle

    def __post_init__(self):
        if self.key not in KEY_CHOICES:
            if self.key:
                logger.warning("Unknown trigger key %r; single-key trigger off", self.key)
            self.key = None
        if self.mouse not in MOUSE_CHOICES:
            if self.mouse:
                logger.warning("Unknown trigger mouse button %r; mouse trigger off", self.mouse)
            self.mouse = None

    def hold_for(self, source: str) -> bool:
        return self.key_hold if source == "key" else self.mouse_hold

    def describe(self) -> list:
        """[(label, mode), ...] for each active trigger, e.g. [('F9', 'hold to talk')]."""
        rows = []
        if self.key:
            rows.append((key_label(self.key), "hold to talk" if self.key_hold else "toggle"))
        if self.mouse:
            rows.append((MOUSE_CHOICES[self.mouse], "hold to talk" if self.mouse_hold else "toggle"))
        return rows


class InputTriggers(QObject):
    """Global single-key + mouse-button trigger. Emits pressed/released(source) — GUI must queue."""

    pressed = pyqtSignal(str)          # "key" or "mouse"
    released = pyqtSignal(str)

    def __init__(self, config: TriggerConfig, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._listeners = []
        self._down = {"key": False, "mouse": False}   # ignore keyboard auto-repeat while held

    # ── Event classification (pure; unit-tested) ──────────────────────────────
    def classify_key(self, msg: int, vk: int) -> Optional[str]:
        """'down' / 'up' if this raw keyboard event is our trigger key, else None."""
        if not self.config.key or vk != KEY_CHOICES[self.config.key]:
            return None
        if msg in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            return "down"
        if msg in (_WM_KEYUP, _WM_SYSKEYUP):
            return "up"
        return None

    def classify_mouse(self, msg: int, mouse_data: int) -> Optional[str]:
        """'down' / 'up' if this raw mouse event is our trigger button, else None."""
        button = self.config.mouse
        if button == "middle":
            return {_WM_MBUTTONDOWN: "down", _WM_MBUTTONUP: "up"}.get(msg)
        if button in _XBUTTON and msg in (_WM_XBUTTONDOWN, _WM_XBUTTONUP):
            if (mouse_data >> 16) & 0xFFFF == _XBUTTON[button]:
                return "down" if msg == _WM_XBUTTONDOWN else "up"
        return None

    def handle(self, source: str, edge: str) -> None:
        """Turn a down/up edge from 'key' or 'mouse' into pressed/released signals."""
        if edge == "down":
            if self._down[source]:     # auto-repeat
                return
            self._down[source] = True
            self.pressed.emit(source)
        elif edge == "up":
            self._down[source] = False
            self.released.emit(source)

    # ── Listeners ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if sys.platform != "win32":
            logger.info("Extra triggers are Windows-only for now; using Ctrl+Alt+Q")
            return
        from pynput import keyboard, mouse
        if self.config.key:
            def key_filter(msg, data):
                edge = self.classify_key(msg, data.vkCode)
                if edge:
                    self.handle("key", edge)
                    kl.suppress_event()        # raises: the focused app never sees it
                return True
            kl = keyboard.Listener(win32_event_filter=key_filter)
            kl.daemon = True
            kl.start()
            self._listeners.append(kl)
        if self.config.mouse:
            def mouse_filter(msg, data):
                edge = self.classify_mouse(msg, data.mouseData)
                if edge:
                    self.handle("mouse", edge)
                    ml.suppress_event()
                return True
            ml = mouse.Listener(win32_event_filter=mouse_filter)
            ml.daemon = True
            ml.start()
            self._listeners.append(ml)
        logger.info("Triggers: %s", ", ".join(f"{a} ({b})" for a, b in self.config.describe()) or "none")

    def stop(self) -> None:
        for listener in self._listeners:
            listener.stop()
        for listener in self._listeners:
            listener.join(timeout=2.0)
        self._listeners = []

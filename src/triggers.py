"""
triggers.py — extra global start/stop triggers for gui_med.py.

Besides Ctrl+Alt+Q (gui_qt.HotkeyBridge), dictation can be toggled with:

  * a single key, default F9      $MYTRANSCRIBE_KEY  = f9 | f8 | ... | f12 | pause | scroll_lock | none
  * a mouse button, default the    $MYTRANSCRIBE_MOUSE = x2 (forward) | x1 (back) | middle | none
    "forward" thumb button
  * either one as toggle (press to start, press to stop) or hold-to-talk:
                                   $MYTRANSCRIBE_TRIGGER_MODE = toggle | hold

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
import os
import sys
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("triggers")

# Windows virtual-key codes for the keys we allow as a single-key trigger.
_VK = {f"f{n}": 0x6F + n for n in range(1, 13)}       # F1 = 0x70 ... F12 = 0x7B
_VK.update({"pause": 0x13, "scroll_lock": 0x91})
_WM_KEYDOWN, _WM_KEYUP, _WM_SYSKEYDOWN, _WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
_WM_MBUTTONDOWN, _WM_MBUTTONUP = 0x0207, 0x0208
_WM_XBUTTONDOWN, _WM_XBUTTONUP = 0x020B, 0x020C
_XBUTTON = {"x1": 1, "x2": 2}

MOUSE_LABELS = {"x2": "mouse forward button", "x1": "mouse back button", "middle": "middle mouse button"}


@dataclass
class TriggerConfig:
    key: Optional[str] = "f9"          # None = no single-key trigger
    mouse: Optional[str] = "x2"        # None = no mouse trigger
    hold: bool = False                 # hold-to-talk instead of toggle

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "TriggerConfig":
        env = os.environ if env is None else env
        key = env.get("MYTRANSCRIBE_KEY", "f9").strip().lower() or "f9"
        mouse = env.get("MYTRANSCRIBE_MOUSE", "x2").strip().lower() or "x2"
        if key not in _VK:
            if key != "none":
                logger.warning("Unknown MYTRANSCRIBE_KEY %r; single-key trigger off", key)
            key = None
        if mouse not in ("x1", "x2", "middle"):
            if mouse != "none":
                logger.warning("Unknown MYTRANSCRIBE_MOUSE %r; mouse trigger off", mouse)
            mouse = None
        hold = env.get("MYTRANSCRIBE_TRIGGER_MODE", "toggle").strip().lower() == "hold"
        return cls(key, mouse, hold)

    def describe(self) -> str:
        """Short human-readable list, e.g. 'F9 · mouse forward button'."""
        parts = []
        if self.key:
            parts.append(self.key.replace("_", " ").title() if len(self.key) > 3 else self.key.upper())
        if self.mouse:
            parts.append(MOUSE_LABELS[self.mouse])
        return " · ".join(parts)


class InputTriggers(QObject):
    """Global single-key + mouse-button trigger. Emits pressed/released (GUI must queue)."""

    pressed = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, config: TriggerConfig, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._listeners = []
        self._down = False             # ignore keyboard auto-repeat while held

    # ── Event classification (pure; unit-tested) ──────────────────────────────
    def classify_key(self, msg: int, vk: int) -> Optional[str]:
        """'down' / 'up' if this raw keyboard event is our trigger key, else None."""
        if not self.config.key or vk != _VK[self.config.key]:
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

    def handle(self, edge: str) -> None:
        """Turn a down/up edge into signals. Toggle mode: only key-down matters."""
        if edge == "down":
            if self._down:             # auto-repeat
                return
            self._down = True
            self.pressed.emit()
        elif edge == "up":
            self._down = False
            if self.config.hold:
                self.released.emit()

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
                    self.handle(edge)
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
                    self.handle(edge)
                    ml.suppress_event()
                return True
            ml = mouse.Listener(win32_event_filter=mouse_filter)
            ml.daemon = True
            ml.start()
            self._listeners.append(ml)
        logger.info("Triggers: %s (%s)", self.config.describe() or "none",
                    "hold-to-talk" if self.config.hold else "toggle")

    def stop(self) -> None:
        for listener in self._listeners:
            listener.stop()
        for listener in self._listeners:
            listener.join(timeout=2.0)
        self._listeners = []

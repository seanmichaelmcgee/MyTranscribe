"""
phi_clipboard.py — clipboard + auto-paste helpers that are careful with PHI.

Windows clipboard history (Win+V) and "sync across devices" keep a copy of
everything copied, and the latter uploads it to Microsoft. Windows honours
three special clipboard formats that opt a single copy out of both:

  ExcludeClipboardContentFromMonitorProcessing   (presence = exclude)
  CanIncludeInClipboardHistory                   DWORD 0 = don't keep in history
  CanUploadToCloudClipboard                      DWORD 0 = don't sync

Qt can write raw Windows formats via the mime type
    application/x-qt-windows-mime;value="<FormatName>"
Paste-into-your-app still works normally; only history/sync skip it.
"""

import logging
import sys
from typing import Dict

logger = logging.getLogger("phi_clipboard")

_DWORD_ZERO = (0).to_bytes(4, "little")
WINDOWS_PRIVACY_FORMATS: Dict[str, bytes] = {
    "ExcludeClipboardContentFromMonitorProcessing": b"\x00",
    "CanIncludeInClipboardHistory": _DWORD_ZERO,
    "CanUploadToCloudClipboard": _DWORD_ZERO,
}


def privacy_mime_entries(platform: str = sys.platform) -> Dict[str, bytes]:
    """Qt mime-type -> payload for the Windows privacy formats ({} elsewhere)."""
    if platform != "win32":
        return {}
    return {
        f'application/x-qt-windows-mime;value="{name}"': payload
        for name, payload in WINDOWS_PRIVACY_FORMATS.items()
    }


def make_mime_data(text: str, platform: str = sys.platform):
    """Build a QMimeData carrying `text` plus the privacy markers."""
    from PyQt6.QtCore import QMimeData, QByteArray
    mime = QMimeData()
    mime.setText(text)
    for mime_type, payload in privacy_mime_entries(platform).items():
        mime.setData(mime_type, QByteArray(payload))
    return mime


def copy_text(clipboard, text: str, platform: str = sys.platform) -> None:
    """Put `text` on a QClipboard with history/cloud-sync opt-out on Windows."""
    clipboard.setMimeData(make_mime_data(text, platform))


_VK_SHIFT, _VK_CONTROL, _VK_MENU = 0x10, 0x11, 0x12


def modifiers_held(platform: str = sys.platform, get_key_state=None) -> bool:
    """
    True if Shift/Ctrl/Alt is physically down right now (Windows only).

    Auto-paste waits for this to become False: if the user is still holding
    the Ctrl+Alt of the stop hotkey, the target app would see Ctrl+Alt+V
    (a different shortcut, or AltGr+V on some keyboard layouts). Releasing
    the keys synthetically instead risks Windows activating a menu bar.
    """
    if platform != "win32":
        return False
    if get_key_state is None:
        import ctypes
        get_key_state = ctypes.windll.user32.GetAsyncKeyState
    return any(get_key_state(vk) & 0x8000 for vk in (_VK_SHIFT, _VK_CONTROL, _VK_MENU))


def send_paste(controller=None, platform: str = sys.platform) -> None:
    """Simulate the paste shortcut in whichever window has keyboard focus."""
    if controller is None:
        from pynput.keyboard import Controller
        controller = Controller()
    from pynput.keyboard import Key
    modifier = Key.cmd if platform == "darwin" else Key.ctrl
    controller.press(modifier)
    try:
        controller.press("v")
        controller.release("v")
    finally:
        controller.release(modifier)

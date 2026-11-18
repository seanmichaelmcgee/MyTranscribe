"""
audio_devices.py — which microphone to record from (Options and the setup wizard).

The app records through Windows' MME audio system (PortAudio's default host API),
which accepts the 16 kHz mono format the model needs from any microphone. MME
cuts device names to 31 characters ("Microphone (Logitech G533 Gamin"), so the
names shown and saved are the full ones from DirectSound where one matches; the
device is then opened by the MME entry whose name starts that full name.

settings.input_device holds the name; "" means the Windows default. A saved
microphone that is not plugged in falls back to the Windows default (logged).
Listing devices never opens one.
"""

import logging
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger("audio_devices")

MME_NAME_LIMIT = 31
_MAPPERS = ("microsoft sound mapper", "primary sound capture driver")
_BT_HINT = re.compile(r"hands-free|bluetooth|bthhfenum", re.I)
# A Bluetooth hands-free entry in the kernel-streaming list, e.g.
# 'Headset (@System32\drivers\bthhfenum.sys,#2;%1 Hands-Free%0\r\n;(OpenFit 2 by Shokz))'
_BT_FRIENDLY = re.compile(r";\(([^()]+)\)\)\s*$")


@dataclass(frozen=True)
class InputDevice:
    name: str            # shown and saved (full name where known)
    index: int           # PortAudio index in the default host API (MME on Windows)
    bluetooth: bool = False


def _pyaudio():
    import pyaudio
    return pyaudio.PyAudio()


def _infos(pa) -> List[dict]:
    out = []
    for i in range(pa.get_device_count()):
        try:
            d = pa.get_device_info_by_index(i)
        except Exception:
            continue
        if d.get("maxInputChannels", 0) > 0:
            out.append(dict(d, index=i))
    return out


def _host_api_index(pa, name: str) -> Optional[int]:
    for i in range(pa.get_host_api_count()):
        try:
            if pa.get_host_api_info_by_index(i).get("name") == name:
                return i
        except Exception:
            continue
    return None


def _full_name(short: str, candidates: List[str]) -> str:
    """The longer name that a 31-character MME name was cut from, if exactly one fits."""
    if len(short) < MME_NAME_LIMIT:
        return short
    fits = sorted({c for c in candidates if c.startswith(short)})
    return fits[0] if len(fits) == 1 else short


def list_inputs(pa=None) -> List[InputDevice]:
    """Microphones in the default host API, in the order Windows lists them (no mappers)."""
    own = pa is None
    pa = pa or _pyaudio()
    try:
        default_api = pa.get_default_host_api_info().get("index")
        infos = _infos(pa)
        ds = _host_api_index(pa, "Windows DirectSound") if sys.platform == "win32" else None
        long_names = [d["name"] for d in infos if ds is not None and d.get("hostApi") == ds]
        bt_friendly = {m.group(1).strip().lower() for d in infos
                       if _BT_HINT.search(d["name"]) and (m := _BT_FRIENDLY.search(d["name"]))}
        out, seen = [], set()
        for d in infos:
            if d.get("hostApi") != default_api or d["name"].strip().lower().startswith(_MAPPERS):
                continue
            name = _full_name(d["name"], long_names).strip()      # the cut can end in a space
            if name in seen:
                continue
            seen.add(name)
            bt = bool(_BT_HINT.search(name)) or any(f in name.lower() for f in bt_friendly)
            out.append(InputDevice(name, d["index"], bt))
        return out
    finally:
        if own:
            pa.terminate()


def input_names(pa=None) -> List[str]:
    """Names for a drop-down; [] if the audio system cannot be read."""
    try:
        return [d.name for d in list_inputs(pa)]
    except Exception as exc:
        logger.warning("Could not list microphones: %s", exc)
        return []


def snapshot() -> Tuple[List[str], str]:
    """(microphone names, the Windows default's name) with one look at the audio system; ([], '') on failure."""
    try:
        pa = _pyaudio()
    except Exception as exc:
        logger.warning("Could not list microphones: %s", exc)
        return [], ""
    try:
        return input_names(pa), default_name(pa)
    finally:
        pa.terminate()


def default_name(pa=None) -> str:
    """The Windows default microphone's name (full where known), or ''."""
    own = pa is None
    try:
        pa = pa or _pyaudio()
        index = pa.get_default_input_device_info().get("index")
        for d in list_inputs(pa):
            if d.index == index:
                return d.name
        return pa.get_default_input_device_info().get("name", "")
    except Exception:
        return ""
    finally:
        if own and pa is not None:
            pa.terminate()


def find_index(pa, name: str) -> Optional[int]:
    """PortAudio index of the saved microphone, or None (not plugged in / never chosen)."""
    if not name:
        return None
    devices = list_inputs(pa)
    for d in devices:
        if d.name == name:
            return d.index
    for d in devices:                       # saved from the other list form (cut or full)
        if name.startswith(d.name) or d.name.startswith(name):
            return d.index
    return None


def is_bluetooth(name: str, pa=None) -> bool:
    if not name:
        return False
    if _BT_HINT.search(name):
        return True
    try:
        return any(d.bluetooth for d in list_inputs(pa) if d.name == name)
    except Exception:
        return False


def open_stream(device: str = "", sample_rate: int = 16000, frames_per_buffer: int = 1024) -> Tuple[object, object]:
    """Open the chosen microphone (or the default) as 16-bit mono. Returns (stream, pyaudio_instance)."""
    import pyaudio
    pa = pyaudio.PyAudio()
    index = None
    try:
        index = find_index(pa, device)
        if device and index is None:
            logger.warning("Chosen microphone not found; using the Windows default")
        info = pa.get_device_info_by_index(index) if index is not None else pa.get_default_input_device_info()
        logger.info("Input device [%s] index=%s", info.get("name"), info.get("index"))
    except (IOError, OSError) as exc:
        logger.warning("Could not query the input device: %s", exc)
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=sample_rate, input=True,
                         frames_per_buffer=frames_per_buffer, input_device_index=index)
    except Exception:
        pa.terminate()
        raise
    return stream, pa

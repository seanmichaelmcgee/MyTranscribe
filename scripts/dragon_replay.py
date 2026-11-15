"""
dragon_replay.py — play the reliability recordings into Dragon Medical One and score its text.

The comparison partner for dictation_reliability.py: the same recordings and the
same derived conditions (thinking pauses, pauses around commands, early Stop),
played in real time through a virtual audio cable into Dragon, with Dragon typing
into a blank Notepad file per recording. Dragon's saved text is then scored with
the same functions as the local pipelines.

What it needs (Windows only):
  * VB-CABLE installed; Dragon's microphone set to "CABLE Output".
  * Dragon Medical One running, signed in, microphone OFF, its bar visible on screen.
  * A hotkey that toggles Dragon's microphone (default: NumPad +).
  * Nobody typing or clicking while it runs: Dragon types into the focused window.

What it does to the desktop: opens Notepad on a new empty file, presses the
microphone hotkey once to start and once to stop (each only after reading the
colour of Dragon's microphone button, never blind), plays the audio, presses
Ctrl+S, then Ctrl+W. Any state it cannot read stops the run. Dragon Medical One
recognises in the cloud, so the audio leaves this computer: use fictional
recordings only.

  python scripts/dragon_replay.py devices
  python scripts/dragon_replay.py state
  python scripts/dragon_replay.py export --corpus-root results_1060 --out results_1060/reliability/dragon --split held
  python scripts/dragon_replay.py run    --out results_1060/reliability/dragon --conditions orig --limit 1
  python scripts/dragon_replay.py score  --corpus-root results_1060 --out results_1060/reliability/dragon --split held

`export` needs the word-timing cache that dictation_reliability.py leaves in
<out>/../word_times, so both tools cut pauses at identical places. A recording
that already has a text file is never played again (`run` skips it; delete the
.txt and .json to repeat one deliberately). Outputs are private: keep --out in
an ignored folder.
"""

import argparse
import json
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SR = 16000
DRAGON_TITLE = "Dragon Medical One"
CABLE_PREFIX = "CABLE Input"
MIC_VK = 0x6B                  # NumPad +
SETTLE_BEFORE_STOP_S = 5.0     # silence Dragon gets before the microphone is switched off
STABLE_READS = 3               # identical saved texts, 1 s apart, before the text counts as final
STABLE_TIMEOUT_S = 20.0
CONDITIONS = ("orig", "pause1.5", "pause4", "cmdpause", "tailpause", "earlystop")


# ── Pure helpers (unit-tested) ───────────────────────────────────────────────
def classify_mic(pixels: np.ndarray) -> str:
    """
    'on' / 'off' / 'unknown' from the left end of Dragon's bar (H x W x 3, BGR):
    the microphone button is green while listening and red while off.
    """
    px = pixels.astype(float)
    b, g, r = px[:, :, 0], px[:, :, 1], px[:, :, 2]
    green = np.count_nonzero((g > 1.2 * r) & (g > 1.2 * b) & (g > 100)) / max(1, g.size)
    red = np.count_nonzero((r > 1.4 * g) & (r > 1.4 * b) & (r > 120)) / max(1, g.size)
    if green > 0.05 and red < 0.01:
        return "on"
    if red > 0.05 and green < 0.01:
        return "off"
    return "unknown"


def clean_text(raw: bytes) -> str:
    """Notepad's saved bytes as text with plain newlines."""
    return raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n").strip()


def cell_name(rec_id: str, cond: str) -> str:
    return f"{rec_id}__{cond}"


def pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


# ── Windows plumbing ─────────────────────────────────────────────────────────
def _user32():
    import ctypes
    from ctypes import wintypes as w
    u = ctypes.windll.user32
    u.GetForegroundWindow.restype = w.HWND
    u.SetForegroundWindow.argtypes = [w.HWND]
    u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    u.IsWindowVisible.argtypes = [w.HWND]
    u.GetDC.argtypes = [w.HWND]
    u.GetDC.restype = w.HDC
    u.ReleaseDC.argtypes = [w.HWND, w.HDC]
    return u


def windows():
    import ctypes
    from ctypes import wintypes as w
    u, out = _user32(), []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(hwnd, _):
        if u.IsWindowVisible(hwnd):
            title, cls = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, title, 1024)
            u.GetClassNameW(hwnd, cls, 256)
            out.append({"hwnd": int(hwnd), "title": title.value, "class": cls.value})
        return True

    u.EnumWindows(visit, 0)
    return out


def one_window(predicate, what: str):
    found = [x for x in windows() if predicate(x)]
    if len(found) != 1:
        raise RuntimeError(f"expected exactly one {what} window, found {len(found)}")
    return found[0]


def grab(hwnd: int) -> np.ndarray:
    """Screen pixels under a window as H x W x 3 (BGR)."""
    import ctypes
    import struct
    from ctypes import wintypes as w
    u, g = _user32(), ctypes.windll.gdi32
    g.CreateCompatibleDC.argtypes = [w.HDC]
    g.CreateCompatibleDC.restype = w.HDC
    g.CreateDIBSection.argtypes = [w.HDC, ctypes.c_void_p, w.UINT, ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD]
    g.CreateDIBSection.restype = w.HBITMAP
    g.SelectObject.argtypes = [w.HDC, w.HANDLE]
    g.SelectObject.restype = w.HANDLE
    g.BitBlt.argtypes = [w.HDC] + [ctypes.c_int] * 4 + [w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD]
    g.DeleteObject.argtypes = [w.HANDLE]
    g.DeleteDC.argtypes = [w.HDC]
    rect = w.RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("could not read the window position")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if not (0 < width < 2400 and 0 < height < 1600):
        raise RuntimeError(f"unexpected window size {width}x{height}")
    info = ctypes.create_string_buffer(struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0,
                                                   width * height * 4, 0, 0, 0, 0))
    dc = u.GetDC(None)
    mem = g.CreateCompatibleDC(dc)
    bits = ctypes.c_void_p()
    bmp = g.CreateDIBSection(dc, info, 0, ctypes.byref(bits), None, 0)
    old = g.SelectObject(mem, bmp)
    try:
        if not g.BitBlt(mem, 0, 0, width, height, dc, rect.left, rect.top, 0x00CC0020):
            raise RuntimeError("screen capture failed")
        raw = ctypes.string_at(bits, width * height * 4)
    finally:
        g.SelectObject(mem, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mem)
        u.ReleaseDC(None, dc)
    return np.frombuffer(raw, np.uint8).reshape(height, width, 4)[:, :, :3]


def mic_state(save_to: Path = None) -> str:
    dragon = one_window(lambda x: x["title"] == DRAGON_TITLE, "Dragon Medical One")
    pixels = grab(dragon["hwnd"])
    if save_to is not None:
        np.save(save_to, pixels)
    height = pixels.shape[0]
    return classify_mic(pixels[:, :int(height * 1.1)])


def desktop_ready():
    """Raise unless the interactive desktop is the one receiving input (not locked)."""
    import ctypes
    from ctypes import wintypes as w
    u = _user32()
    u.OpenInputDesktop.restype = w.HANDLE
    handle = u.OpenInputDesktop(0, False, 1)
    if not handle:
        raise RuntimeError("input desktop unavailable (locked?); no keys sent")
    try:
        name, needed = ctypes.create_unicode_buffer(256), w.DWORD()
        u.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(needed))
        if name.value != "Default":
            raise RuntimeError("screen is locked; no keys sent")
    finally:
        u.CloseDesktop(handle)


class Desk:
    """The Notepad target and the keys sent to it. Keys go out only while it is the foreground window."""

    def __init__(self, target: Path, mic_vk: int):
        from pynput.keyboard import Controller, Key, KeyCode
        self.target, self.keys, self.Key = target, Controller(), Key
        self.mic_key = KeyCode.from_vk(mic_vk)

    def window(self):
        return one_window(lambda x: self.target.stem in x["title"] and "Notepad" in x["class"], "target Notepad")

    def focus(self):
        desktop_ready()
        u, own = _user32(), self.window()
        for _ in range(3):
            u.SetForegroundWindow(own["hwnd"])
            time.sleep(0.3)
            if int(u.GetForegroundWindow() or 0) == own["hwnd"]:
                return
            self.keys.press(self.Key.alt)      # Windows lets a process that just sent input take focus
            self.keys.release(self.Key.alt)
        raise RuntimeError("could not bring the target Notepad window to the front; no keys sent")

    def toggle_mic(self, want: str, settle_s: float = 0.0):
        """One hotkey press, only from the opposite known state; verified by the button colour."""
        before = mic_state()
        if before not in ("on", "off") or before == want:
            raise RuntimeError(f"microphone is '{before}', expected the opposite of '{want}'; no key sent")
        if settle_s:
            time.sleep(settle_s)
        self.focus()
        self.keys.press(self.mic_key)
        time.sleep(0.08)
        self.keys.release(self.mic_key)
        sent = time.monotonic()
        for _ in range(12):
            time.sleep(0.5)
            if mic_state() == want:
                return sent
        raise RuntimeError(f"microphone did not switch {want}; not pressing again")

    def save(self) -> bytes:
        self.focus()
        with self.keys.pressed(self.Key.ctrl):
            self.keys.press("s")
            self.keys.release("s")
        time.sleep(0.5)
        return self.target.read_bytes()

    def close(self):
        self.focus()
        with self.keys.pressed(self.Key.ctrl):
            self.keys.press("w")
            self.keys.release("w")


def cable_output(pa):
    """The single MME 'CABLE Input' playback device (what Dragon hears as 'CABLE Output')."""
    found = []
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if (d["maxOutputChannels"] > 0 and d["name"].startswith(CABLE_PREFIX)
                and pa.get_host_api_info_by_index(d["hostApi"])["name"] == "MME"):
            found.append(d)
    if len(found) != 1:
        raise RuntimeError(f"expected one '{CABLE_PREFIX}' playback device, found {len(found)}; is VB-CABLE installed?")
    return found[0]


def play(pcm: bytes) -> float:
    """Play 16 kHz mono PCM16 into the cable in real time; returns seconds taken."""
    import pyaudio
    pa = pyaudio.PyAudio()
    stream = None
    try:
        device = cable_output(pa)
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SR, output=True,
                         output_device_index=int(device["index"]), frames_per_buffer=1024)
        start = time.monotonic()
        for offset in range(0, len(pcm), 2048):
            stream.write(pcm[offset:offset + 2048], exception_on_underflow=False)
        stream.stop_stream()
        return time.monotonic() - start
    finally:
        if stream is not None:
            stream.close()
        pa.terminate()


# ── Commands ─────────────────────────────────────────────────────────────────
def cmd_devices(_args):
    import pyaudio
    pa = pyaudio.PyAudio()
    try:
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if "CABLE" in d["name"].upper():
                api = pa.get_host_api_info_by_index(d["hostApi"])["name"]
                print(f"{i:3d} {api:12s} in={d['maxInputChannels']} out={d['maxOutputChannels']} {d['name']}")
        print("playback device:", cable_output(pa)["name"])
    finally:
        pa.terminate()


def cmd_state(args):
    print("Dragon microphone:", mic_state(args.save))


def cmd_export(args):
    """Write every condition's audio as WAV plus cells.json. No model, no playback."""
    import dictation_reliability as rel
    from bench_engine import load_wav
    cache_dir = args.out.parent / "word_times"
    audio_dir = args.out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    cells = []
    for e in rel.load_corpus(args.corpus_root, args.split):
        audio = load_wav(e["wav"])
        words = rel.cached_word_times(cache_dir, audio)
        for cond in args.conditions.split(","):
            built = rel.build_condition(cond, audio, words)
            if built is None:
                continue
            cond_audio, stop_at, sites = built
            if stop_at is not None:          # early Stop: the audio ends there and the mic goes off at once
                cond_audio = cond_audio[:stop_at]
            name = cell_name(e["id"], cond)
            with wave.open(str(audio_dir / f"{name}.wav"), "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(SR)
                f.writeframes(pcm16(cond_audio))
            cells.append({"name": name, "id": e["id"], "condition": cond, "sites": sites,
                          "audio_s": round(len(cond_audio) / SR, 2), "stop_at_end": stop_at is not None})
    (args.out / "cells.json").write_text(json.dumps(cells, indent=1), encoding="utf-8")
    minutes = sum(c["audio_s"] for c in cells) / 60
    print(f"{len(cells)} cells, {minutes:.1f} min of audio -> {args.out}")


def run_cell(cell, out: Path, mic_vk: int):
    text_dir = out / "text"
    text_dir.mkdir(exist_ok=True)
    target = text_dir / f"{cell['name']}.txt"
    receipt = {"cell": cell, "started_utc": datetime.now(timezone.utc).isoformat(), "complete": False}
    desk, mic_on = Desk(target, mic_vk), False
    try:
        desktop_ready()
        if mic_state() != "off":
            raise RuntimeError("Dragon's microphone is not positively off before the recording")
        with wave.open(str(out / "audio" / f"{cell['name']}.wav"), "rb") as f:
            if (f.getnchannels(), f.getsampwidth(), f.getframerate()) != (1, 2, SR):
                raise RuntimeError("audio must be 16 kHz mono PCM16")
            pcm = f.readframes(f.getnframes())
        target.touch(exist_ok=False)
        subprocess.Popen(["notepad.exe", str(target)])
        time.sleep(2.0)
        desk.toggle_mic("on")
        mic_on = True
        time.sleep(1.0)
        desk.focus()
        receipt["playback_s"] = round(play(pcm), 2)
        desk.toggle_mic("off", settle_s=0.0 if cell["stop_at_end"] else SETTLE_BEFORE_STOP_S)
        mic_on = False
        deadline, seen = time.monotonic() + STABLE_TIMEOUT_S, []
        while time.monotonic() < deadline:
            time.sleep(1.0)
            seen.append(desk.save())
            if len(seen) >= STABLE_READS and len(set(seen[-STABLE_READS:])) == 1:
                break
        else:
            raise RuntimeError("saved text kept changing")
        if not seen[-1].strip():
            raise RuntimeError("Dragon produced no text")
        receipt.update(text_bytes=len(seen[-1]), saves=len(seen), complete=True)
        desk.close()
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if mic_on:
            try:
                if mic_state() == "on":
                    desk.toggle_mic("off", settle_s=SETTLE_BEFORE_STOP_S)
            except Exception as exc:      # leave it for the operator; never press blind
                receipt["cleanup_error"] = str(exc)
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (text_dir / f"{cell['name']}.json").write_text(json.dumps(receipt, indent=1), encoding="utf-8")


def cmd_run(args):
    cells = json.loads((args.out / "cells.json").read_text(encoding="utf-8"))
    wanted = args.conditions.split(",")
    todo = [c for c in cells if c["condition"] in wanted and (not args.only or args.only in c["id"])
            and not (args.out / "text" / f"{c['name']}.txt").exists()]
    todo.sort(key=lambda c: wanted.index(c["condition"]))
    todo = todo[:args.limit] if args.limit else todo
    print(f"{len(todo)} to play, {sum(c['audio_s'] for c in todo) / 60:.1f} min of audio", flush=True)
    for n, cell in enumerate(todo, 1):
        run_cell(cell, args.out, args.mic_vk)       # any failure stops the run; nothing is replayed
        print(f"{n}/{len(todo)} done ({cell['audio_s']:.0f} s)", flush=True)   # no ids or text in the log
        time.sleep(1.0)


def cmd_score(args):
    import dictation_reliability as rel
    entries = {e["id"]: e for e in rel.load_corpus(args.corpus_root, args.split)}
    cells = json.loads((args.out / "cells.json").read_text(encoding="utf-8"))
    texts = {}
    for c in cells:
        path = args.out / "text" / f"{c['name']}.txt"
        receipt = args.out / "text" / f"{c['name']}.json"
        if path.is_file() and receipt.is_file() and json.loads(receipt.read_text(encoding="utf-8"))["complete"]:
            texts[c["name"]] = clean_text(path.read_bytes())
    rows = []
    for c in cells:
        e = entries.get(c["id"])
        if e is None or c["name"] not in texts:
            continue
        base = texts.get(cell_name(c["id"], "orig"))
        rows.append(rel.score_row(e, c["condition"], texts[c["name"]], base, c["audio_s"], sites=c["sites"]))
    summary = rel.summarise(rows, rel.CONDITIONS)
    runs = args.out.parent / "runs"
    runs.mkdir(exist_ok=True)
    (runs / f"dragon__{args.split}.json").write_text(json.dumps(
        {"profile": "dragon", "split": args.split, "summary": summary, "rows": rows},
        indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"profile=dragon split={args.split} ({len(rows)} of {len(cells)} cells scored)")
    rel.print_summary(summary)


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("devices").set_defaults(func=cmd_devices)
    p = sub.add_parser("state")
    p.add_argument("--save", type=Path, help="also save the captured pixels (.npy)")
    p.set_defaults(func=cmd_state)
    for name, func in (("export", cmd_export), ("run", cmd_run), ("score", cmd_score)):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True, type=Path)
        if name != "run":
            p.add_argument("--corpus-root", required=True, type=Path)
            p.add_argument("--split", default="held", choices=["dev", "held", "all"])
        if name != "score":
            p.add_argument("--conditions", default=",".join(CONDITIONS[:-1]))
        if name == "run":
            p.add_argument("--only", help="substring of recording ids to keep")
            p.add_argument("--limit", type=int, default=0)
            p.add_argument("--mic-vk", type=lambda s: int(s, 0), default=MIC_VK,
                           help="virtual-key code of Dragon's microphone hotkey (default 0x6B, NumPad +)")
        p.set_defaults(func=func)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

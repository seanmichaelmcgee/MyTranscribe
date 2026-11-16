"""
Side-by-side validation against Dragon on a fictional reading set.

You read each item of validation/validation_set_v1.txt aloud once. Dragon types
what it hears into this tool's window while the tool records the same
microphone. Afterwards the saved audio is run through each local recogniser in
turn, and all of them are scored against the text you were asked to read.

    validation_tool.py show                       print the set as you would dictate it
    validation_tool.py record --out <folder>      the reading session (a window)
    validation_tool.py score  --out <folder>      run Whisper, then MedASR, and score all three

Everything stays in --out on this PC: one WAV and one Dragon text per item, then
results.json and results.csv. Nothing is sent anywhere; the recognisers run
with the Hugging Face hub offline. The set is invented text, so the recordings
hold no patient information. Do NOT point this at real dictation: that needs
the counts-only mode described in docs/VALIDATION.md.

Reading tips: click Start (or press F8), switch Dragon's microphone on, read the
item including the words in CAPITALS, switch Dragon's microphone off, wait for
Dragon to finish typing, then Stop (F8). Redo an item if you stumbled.
"""

import argparse
import csv
import json
import re
import sys
import threading
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_SET = ROOT / "validation" / "validation_set_v1.txt"
SR = 16000
_TITLES = ("Mr", "Mrs", "Ms", "Dr", "Miss")
_SAID = {".": "period", ",": "comma", ":": "colon", ";": "semicolon", "?": "question mark"}


# ── The set ──────────────────────────────────────────────────────────────────
def parse_set(text: str) -> list:
    """[{id, category, reference}] from the "## id | kind" format."""
    items, current = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            ident, _, kind = line[3:].partition("|")
            current = {"id": ident.strip(), "category": kind.strip() or "short", "lines": []}
            items.append(current)
        elif current is not None:
            current["lines"].append(line)
    for item in items:
        item["reference"] = "\n".join(item.pop("lines")).strip()
        item["spoken"] = spoken_form(item["reference"])
    return items


def spoken_form(reference: str, shout: bool = False) -> str:
    """
    The text as it is dictated: every mark and break said as a word. With
    shout=True the dictated words are in CAPITALS so they are easy to read out.
    """
    say = (lambda w: w.upper()) if shout else (lambda w: w)
    text = reference
    text = re.sub(r"(\d)/(\d)", r"\1 over \2", text)
    text = re.sub(r"(\d)%", r"\1 percent", text)
    text = re.sub(r'"([^"\n]*)"', lambda m: f" {say('open quote')} {m.group(1)} {say('close quote')}", text)
    text = re.sub(r"(?m)^(\d{1,2})\. ", lambda m: f"{m.group(1)} {say('period')} ", text)   # list numbers
    titles = "".join(rf"(?<!\b{t})" for t in _TITLES)                              # "Dr." has no spoken mark
    text = re.sub(titles + r"([.,:;?])(?=\s|$)", lambda m: f" {say(_SAID[m.group(1)])}", text)   # not decimals
    text = re.sub(r"[ \t]*\n[ \t]*\n[ \t]*", f" {say('new paragraph')} ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", f" {say('new line')} ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def load_set(path: Path) -> list:
    return parse_set(path.read_text(encoding="utf-8"))


# ── show ─────────────────────────────────────────────────────────────────────
def cmd_show(args):
    for item in load_set(args.set):
        print(f"[{item['id']}]  {spoken_form(item['reference'], shout=True)}\n")


# ── record ───────────────────────────────────────────────────────────────────
class Recorder:
    """Microphone to memory between start() and stop(); 16 kHz mono int16."""

    def __init__(self, cable: bool = False):
        self.cable = cable
        self._frames, self._run, self._thread = [], False, None
        self.error = None

    def _open(self):
        import pyaudio
        pa = pyaudio.PyAudio()
        index = None
        if self.cable:                                   # self-test: the virtual cable is the microphone
            found = [d for d in (pa.get_device_info_by_index(i) for i in range(pa.get_device_count()))
                     if d["maxInputChannels"] > 0 and d["name"].startswith("CABLE Output")
                     and pa.get_host_api_info_by_index(d["hostApi"])["name"] == "MME"]
            index = int(found[0]["index"])
        return pa, pa.open(format=pyaudio.paInt16, channels=1, rate=SR, input=True,
                           input_device_index=index, frames_per_buffer=1024)

    def start(self):
        self._frames, self._run, self.error = [], True, None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        try:
            pa, stream = self._open()
            try:
                while self._run:
                    self._frames.append(stream.read(1024, exception_on_overflow=False))
            finally:
                stream.stop_stream()
                stream.close()
                pa.terminate()
        except Exception as exc:                          # shown in the window, never raised in the thread
            self.error = str(exc) or exc.__class__.__name__

    def stop(self) -> bytes:
        self._run = False
        if self._thread is not None:
            self._thread.join(timeout=5)
        return b"".join(self._frames)


class NativeEdit:
    """
    A standard Windows multi-line EDIT control placed over a Qt widget. Dragon
    only types into controls it recognises; a Qt text box is not one of them,
    the plain Windows edit control is.
    """
    WS_CHILD, WS_VISIBLE, WS_VSCROLL, WS_BORDER = 0x40000000, 0x10000000, 0x00200000, 0x00800000
    ES_MULTILINE, ES_AUTOVSCROLL, ES_WANTRETURN = 0x0004, 0x0040, 0x1000
    WM_SETFONT = 0x0030

    def __init__(self, host):
        import ctypes
        from ctypes import wintypes as w
        self.u, self.host = ctypes.windll.user32, host
        self.u.CreateWindowExW.restype = w.HWND
        self.u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
        self.u.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        self.u.SetFocus.argtypes = self.u.GetWindowTextLengthW.argtypes = [w.HWND]
        self.u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        self.u.SetWindowTextW.argtypes = [w.HWND, w.LPCWSTR]
        self.u.MoveWindow.argtypes = [w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.BOOL]
        style = (self.WS_CHILD | self.WS_VISIBLE | self.WS_VSCROLL | self.WS_BORDER | self.ES_MULTILINE
                 | self.ES_AUTOVSCROLL | self.ES_WANTRETURN)
        self.hwnd = self.u.CreateWindowExW(0, "EDIT", "", style, 0, 0, 100, 100, int(host.winId()), None, None, None)
        if not self.hwnd:
            raise RuntimeError("could not create the Windows edit control for Dragon")
        gdi = ctypes.windll.gdi32
        gdi.CreateFontW.restype = w.HFONT
        self._font = gdi.CreateFontW(-22, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self.u.SendMessageW(self.hwnd, self.WM_SETFONT, self._font, 1)
        self.fit()

    def fit(self):
        ratio = self.host.devicePixelRatioF()
        self.u.MoveWindow(self.hwnd, 0, 0, int(self.host.width() * ratio), int(self.host.height() * ratio), True)

    def text(self) -> str:
        import ctypes
        n = self.u.GetWindowTextLengthW(self.hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        self.u.GetWindowTextW(self.hwnd, buf, n + 1)
        return buf.value.replace("\r\n", "\n")

    def set_text(self, text: str):
        self.u.SetWindowTextW(self.hwnd, text.replace("\r\n", "\n").replace("\n", "\r\n"))

    def focus(self):
        self.u.SetFocus(self.hwnd)


def save_wav(path: Path, pcm: bytes):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def cmd_record(args):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont, QKeySequence, QShortcut
    from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

    items = load_set(args.set)
    out = args.out
    (out / "items").mkdir(parents=True, exist_ok=True)
    recorder = Recorder(cable=args.input == "cable")
    app = QApplication.instance() or QApplication([])

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("MyTranscribe validation: read, Dragon types here")
            self.resize(900, 720)
            self.index = next((i for i, it in enumerate(items) if not self.done(it)), len(items))
            self.recording = False
            self.started = 0.0
            layout = QVBoxLayout(self)
            self.header = QLabel()
            layout.addWidget(self.header)
            self.script = QTextEdit()
            self.script.setReadOnly(True)
            self.script.setFont(QFont("Segoe UI", 15))
            layout.addWidget(self.script, 3)
            layout.addWidget(QLabel("Dragon types here (keep the cursor in this box while you dictate):"))
            self.dragon_host = QWidget()
            self.dragon_host.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
            self.dragon_host.setMinimumHeight(170)
            layout.addWidget(self.dragon_host, 2)
            self.dragon = None                              # the native control, made once the window exists
            self._f8_down = False
            row = QHBoxLayout()
            self.toggle = QPushButton()
            self.toggle.clicked.connect(self.on_toggle)
            self.redo = QPushButton("Redo this item")
            self.redo.clicked.connect(self.on_redo)
            self.back = QPushButton("Back")
            self.back.clicked.connect(lambda: self.go(self.index - 1))
            self.next = QPushButton("Next")
            self.next.clicked.connect(lambda: self.go(self.index + 1))
            for b in (self.toggle, self.redo, self.back, self.next):
                row.addWidget(b)
            layout.addLayout(row)
            self.status = QLabel()
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            QShortcut(QKeySequence("F8"), self, activated=self.on_toggle)
            self.keys = QTimer(self)                        # F8 while the cursor is in Dragon's (native) box
            self.keys.setInterval(30)
            self.keys.timeout.connect(self.poll_f8)
            self.keys.start()
            self.tick = QTimer(self)
            self.tick.setInterval(250)
            self.tick.timeout.connect(self.refresh_status)
            self.tick.start()
        def showEvent(self, event):
            super().showEvent(event)
            if self.dragon is None:
                self.dragon = NativeEdit(self.dragon_host)
                self.show_item()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self.dragon is not None:
                self.dragon.fit()

        def poll_f8(self):
            import ctypes
            down = bool(ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000)
            fired = down and not self._f8_down and self.isActiveWindow() and self.dragon is not None \
                and ctypes.windll.user32.GetFocus() == self.dragon.hwnd
            self._f8_down = down
            if fired:
                self.on_toggle()

        @staticmethod
        def paths(item):
            return out / "items" / f"{item['id']}.wav", out / "items" / f"{item['id']}.dragon.txt"

        def done(self, item):
            return all(p.is_file() for p in self.paths(item))

        def go(self, index):
            if not self.recording:
                self.index = max(0, min(len(items), index))
                self.show_item()

        def show_item(self):
            if self.dragon is None:
                return
            finished = sum(self.done(it) for it in items)
            if self.index >= len(items):
                self.header.setText(f"All items shown. {finished} of {len(items)} recorded.")
                self.script.setPlainText("Finished. Close this window, then run:\n\n"
                                         f"    validation_tool.py score --out {out}")
                self.dragon.set_text("")
                self.toggle.setEnabled(False)
                return
            item = items[self.index]
            self.toggle.setEnabled(True)
            self.header.setText(f"Item {self.index + 1} of {len(items)}  [{item['id']}, {item['category']}]"
                                f"   recorded so far: {finished}")
            self.script.setPlainText(spoken_form(item["reference"], shout=True))
            wav, txt = self.paths(item)
            self.dragon.set_text(txt.read_text(encoding="utf-8") if txt.is_file() else "")
            self.toggle.setText("Start (F8)")
            self.dragon.focus()

        def on_redo(self):
            if self.recording or self.index >= len(items):
                return
            for p in self.paths(items[self.index]):
                p.unlink(missing_ok=True)
            self.show_item()

        def on_toggle(self):
            if self.index >= len(items):
                return
            item = items[self.index]
            if not self.recording:
                self.dragon.set_text("")
                recorder.start()
                self.recording, self.started = True, time.monotonic()
                self.toggle.setText("Stop (F8)")
                self.dragon.focus()
                return
            pcm = recorder.stop()
            self.recording = False
            wav, txt = self.paths(item)
            if recorder.error or len(pcm) < SR:            # under half a second: nothing usable
                self.status.setText(f"Recording failed: {recorder.error or 'no audio captured'}. Try again.")
                self.toggle.setText("Start (F8)")
                return
            save_wav(wav, pcm)
            txt.write_text(self.dragon.text(), encoding="utf-8")
            self.go(self.index + 1)

        def refresh_status(self):
            if self.recording:
                self.status.setText(f"RECORDING {time.monotonic() - self.started:4.0f} s. Dragon microphone on, read the "
                                    "item with the words in CAPITALS, Dragon microphone off, wait for Dragon to "
                                    "finish typing, then Stop (F8).")
            elif not self.status.text().startswith("Recording failed"):
                self.status.setText("Not recording. Start (F8) clears the Dragon box and begins the item.")

    window = Window()
    window.show()
    if args.autoplay:
        _autoplay(app, window, items, Path(args.autoplay))
    else:
        app.exec()


def _autoplay(app, window, items, audio_dir: Path):
    """Self-test: play <audio_dir>/<id>.wav through the virtual cable with Dragon's microphone on."""
    import numpy as np
    from pynput.keyboard import Controller, Key, KeyCode
    import dragon_replay as dg
    keys, mic = Controller(), KeyCode.from_vk(dg.MIC_VK)

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    def front():
        """Keys go out only while this window is the foreground one, with the cursor in Dragon's box."""
        dg.desktop_ready()
        u, own = dg._user32(), int(window.winId())
        for _ in range(3):
            u.SetForegroundWindow(own)
            pump(0.3)
            if int(u.GetForegroundWindow() or 0) == own:
                window.dragon.focus()
                pump(0.2)
                return
            keys.press(Key.alt)
            keys.release(Key.alt)
        raise SystemExit("could not bring the validation window to the front; no keys sent")

    def press(want):
        if dg.mic_state() == want:
            raise SystemExit(f"Dragon microphone is already {want}; stopping")
        front()
        keys.press(mic)
        time.sleep(0.08)
        keys.release(mic)
        for _ in range(12):
            pump(0.5)
            if dg.mic_state() == want:
                return
        raise SystemExit(f"Dragon microphone did not switch {want}")

    pump(1.0)
    for item in items:
        source = audio_dir / f"{item['id']}.wav"
        if window.done(item) or not source.is_file():
            continue
        window.go(items.index(item))
        with wave.open(str(source)) as w:
            pcm = w.readframes(w.getnframes())
        window.on_toggle()
        press("on")
        player = threading.Thread(target=dg.play, args=(pcm,), daemon=True)
        player.start()
        while player.is_alive():
            pump(0.1)
        pump(5.0)
        press("off")
        last = None
        for _ in range(20):                               # wait for Dragon to finish typing
            pump(1.0)
            now = window.dragon.text()
            if now == last:
                break
            last = now
        window.on_toggle()
        words = len(window.paths(item)[1].read_text(encoding="utf-8").split())
        print(f"{item['id']} recorded, Dragon wrote {words} words", flush=True)
    window.close()


# ── score ────────────────────────────────────────────────────────────────────
PROFILES = {"whisper": "candidate_full", "medasr": "classic_full", "parakeet": "classic_full", "canary": "classic_full"}


def transcribe_all(engine_name: str, items: list, out: Path, model=None) -> dict:
    """{id: text} from the saved recordings, through the app's pipeline with the text options on."""
    import dictation_reliability as dr
    import engines
    from bench_engine import load_wav

    cache = out / f"local_{engine_name}.json"
    done = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else {}
    todo = [it for it in items if it["id"] not in done and (out / "items" / f"{it['id']}.wav").is_file()]
    if not todo:
        return done
    if model and engine_name == "whisper":
        import os
        os.environ["MYTRANSCRIBE_MODEL"] = str(model)
    engine = engines.build(engine_name)
    profile = dr.PROFILES[PROFILES[engine_name]]
    style = dr.load_prompt()
    builder, post = dr.build_text_pipeline(style, count=getattr(engine, "count_tokens", None), env={})
    for it in todo:
        audio = load_wav(out / "items" / f"{it['id']}.wav")
        text = dr.run_pipeline(engine, audio, None, style, builder, post, profile)[0]
        if getattr(engine, "writes_marker_words", False):
            pass                                          # classic_full already converts dictated marks
        done[it["id"]] = text
        cache.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  {engine_name} {it['id']}", flush=True)
    del engine
    import gc
    gc.collect()
    return done


def cmd_score(args):
    import dictation_reliability as dr
    import engines

    items = [it for it in load_set(args.set) if (args.out / "items" / f"{it['id']}.dragon.txt").is_file()]
    if not items:
        raise SystemExit(f"no recorded items in {args.out}; run 'record' first")
    systems = {"dragon": {it["id"]: (args.out / "items" / f"{it['id']}.dragon.txt").read_text(encoding="utf-8")
                          for it in items}}
    for name in args.engines.split(","):
        ok, why = engines.availability(name)
        if not ok:
            print(f"skipping {name}: {why}")
            continue
        print(f"running {name} on {len(items)} recordings ...", flush=True)
        systems[name] = transcribe_all(name, items, args.out, args.model)

    result, table = {"items": len(items), "systems": {}}, []
    for name, texts in systems.items():
        rows = [dr.score_row({"id": it["id"], "split": "validation", "category": it["category"],
                              "reference": it["reference"], "spoken": it["spoken"]},
                             "orig", texts.get(it["id"], ""), texts.get(it["id"], ""), audio_s=0.0)
                for it in items]
        by_kind = {}
        for kind in ("short", "consult", "all"):
            sel = [r for r in rows if kind == "all" or r["category"] == kind]
            if sel:
                by_kind[kind] = dr.summarise(sel, ["orig"])["orig"]
        result["systems"][name] = {"summary": by_kind, "rows": rows}
        for r in rows:
            table.append({"system": name, "id": r["id"], "kind": r["category"], "ref_words": r["ref_words"],
                          "errors": r["errors"], "format_ok": r["format_ok"], "tail_ok": r["tail_ok"]})
    (args.out / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    with (args.out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)

    print(f"\n{len(items)} items scored against the text that was read (word errors ignore punctuation marks)")
    print(f"{'system':10s} {'kind':8s} {'n':>3s} {'WER %':>7s} {'format ok':>10s} {'commands':>10s} {'last words':>11s}")
    for name, data in result["systems"].items():
        for kind, s in data["summary"].items():
            print(f"{name:10s} {kind:8s} {s['recordings']:3d} {s['wer']:7.2f} {s['format']:>10s} "
                  f"{s['commands']:>10s} {s['tail']:>11s}")
    print(f"\nresults: {args.out / 'results.json'} and results.csv")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, func in (("show", cmd_show), ("record", cmd_record), ("score", cmd_score)):
        p = sub.add_parser(name)
        p.add_argument("--set", type=Path, default=DEFAULT_SET)
        p.set_defaults(func=func)
        if name != "show":
            p.add_argument("--out", required=True, type=Path)
        if name == "record":
            p.add_argument("--input", default="microphone", choices=["microphone", "cable"])
            p.add_argument("--autoplay", help="self-test: folder of <id>.wav to play through the virtual cable")
        if name == "score":
            p.add_argument("--engines", default="whisper,medasr")
            p.add_argument("--model", help="local Whisper model folder")
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

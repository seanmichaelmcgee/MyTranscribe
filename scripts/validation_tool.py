"""
Side-by-side validation against Dragon on a fictional reading set.

You read each item of validation/validation_set_v1.txt aloud once. Dragon types
what it hears into this tool's window while the tool records the same
microphone. Afterwards the saved audio is run through each local recogniser in
turn, and all of them are scored against the text you were asked to read.

    validation_tool.py show                       print the set as you would dictate it
    validation_tool.py record --out <folder>      the reading session (a window)
    validation_tool.py score  --out <folder>      run Whisper, then MedASR, and score all three
    validation_tool.py import --from <folder> --out <folder>
                                                  take recordings made elsewhere, e.g. from a shared Google
                                                  Drive folder, and prepare them for "score". Easiest: ONE
                                                  long recording of the whole script, saying "break break"
                                                  between items; it is cut up and each piece is matched to
                                                  its item by what was said. Files named by item code
                                                  (s01.m4a, c03.wav) are also accepted.

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
# The set and its dictated form live in src/tuning/sets.py, shared with the setup wizard.
from tuning.sets import load_set, parse_set, set_language, spoken_form  # noqa: E402,F401


# ── show ─────────────────────────────────────────────────────────────────────
def cmd_show(args):
    for item in load_set(args.set):
        print(f"[{item['id']}]  {spoken_form(item['reference'], shout=True, language=item['language'])}\n")


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
            self.script.setPlainText(spoken_form(item["reference"], shout=True, language=item["language"]))
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


# ── import ───────────────────────────────────────────────────────────────────
AUDIO = (".wav", ".m4a", ".mp3", ".mp4", ".aac", ".ogg", ".opus", ".flac", ".wma", ".webm")


BREAK_WORDS = ("break", "brake", "breaks", "brakes")
SORRY_WORDS = {"sorry", "oops", "again", "correction"}   # said before "break break" to abandon a false start
BREAK_MAX_GAP_S = 1.5          # the two words of "break break" are said together
MATCH_MIN = 0.35               # a piece must share at least this much of an item's opening words
PAD_S = 0.2


def _plain(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def find_breaks(words: list) -> list:
    """[(start_s, end_s)] of each spoken "break break" in [(word, start, end)]."""
    out, i = [], 0
    while i < len(words) - 1:
        if (_plain(words[i][0]) in BREAK_WORDS and _plain(words[i + 1][0]) in BREAK_WORDS
                and words[i + 1][1] - words[i][2] <= BREAK_MAX_GAP_S):
            j = i + 1
            while j + 1 < len(words) and _plain(words[j + 1][0]) in BREAK_WORDS \
                    and words[j + 1][1] - words[j][2] <= BREAK_MAX_GAP_S:
                j += 1                                  # "break break break" is still one break
            out.append((words[i][1], words[j][2]))
            i = j + 1
        else:
            i += 1
    return out


def _drop_false_start(inside: list, following: list) -> list:
    """
    "... thank you period. Thank you for seeing Mrs. Sorry, break break. Thank you for
    seeing Mrs. Whitcombe ...": the words after the item's end are the next item begun
    and abandoned. If the stretch ends with the opening words of the next stretch, cut
    them (and the "sorry") off.
    """
    opening = [_plain(w[0]) for w in following[:3]]
    plain = [_plain(w[0]) for w in inside]
    if len(opening) < 3 or not set(plain[-2:]) & SORRY_WORDS:
        return inside                   # only after a spoken "sorry": many items end as the next one begins
    for k in range(len(plain) - 3, max(len(plain) - 30, 0), -1):
        if plain[k:k + 3] == opening and k >= 2:
            return inside[:k]
    return inside


def split_pieces(words: list, audio_s: float) -> list:
    """[(start_s, end_s, text)] for the stretches between breaks that contain speech."""
    edges = [0.0]
    for start, end in find_breaks(words):
        edges += [start, end]
    edges.append(audio_s)
    stretches = [[w for w in words if w[1] >= a - 0.01 and w[2] <= b + 0.01]
                 for a, b in zip(edges[0::2], edges[1::2])]
    limits = list(zip(edges[0::2], edges[1::2]))
    pieces = []
    for n, inside in enumerate(stretches):
        if n + 1 < len(stretches):
            inside = _drop_false_start(inside, stretches[n + 1])
        if len(inside) >= 2:
            a, b = limits[n]
            # Stay clear of the break words on both sides: a clip that catches the start of
            # "break" gets it transcribed as a word of the item.
            start = max(a + 0.05 if a > 0 else 0.0, inside[0][1] - PAD_S)
            last = inside[-1][2]
            end = min(last + PAD_S, b - 0.05 if b < audio_s else audio_s)
            end = max(end, min(last + 0.1, audio_s))        # word ends are timed a little early: never cut at one
            pieces.append((start, end, " ".join(w[0].strip() for w in inside)))
    return pieces


def match_pieces(pieces: list, items: list) -> dict:
    """
    {item id: piece index}. Each piece goes to the item whose dictated text it
    most resembles; when an item was read twice, the later reading wins (so a
    stumble is fixed by just reading the item again).
    """
    import difflib
    spoken = {it["id"]: [_plain(w) for w in it["spoken"].split()] for it in items}
    chosen = {}
    for n, (_a, _b, text) in enumerate(pieces):
        heard = [_plain(w) for w in text.split() if _plain(w)]
        best, score = None, 0.0
        for code, want in spoken.items():
            size = max(8, min(len(want), len(heard), 60))
            ratio = difflib.SequenceMatcher(None, want[:size], heard[:size], autojunk=False).ratio()
            ratio *= min(1.0, len(heard) / max(1, 0.8 * len(want)))     # a false start is not the item
            if ratio > score:
                best, score = code, ratio
        if best is not None and score >= MATCH_MIN:
            chosen[best] = n
    return chosen


def split_recording(path: Path, items: list, out: Path, engine) -> list:
    """Cut one long recording at each "break break" and save the pieces as <out>/items/<code>.wav."""
    import numpy as np
    audio = load_audio(path)
    segments, _ = engine.model.transcribe(audio, language="en", word_timestamps=True, vad_filter=True,
                                          condition_on_previous_text=False,
                                          initial_prompt="Period. New paragraph. Break, break.")
    words = [(w.word, float(w.start), float(w.end)) for seg in segments for w in (seg.words or [])]
    pieces = split_pieces(words, len(audio) / SR)
    chosen = match_pieces(pieces, items)
    for code, n in chosen.items():
        a, b, _text = pieces[n]
        clip = audio[int(a * SR):int(b * SR)]
        save_wav(out / "items" / f"{code}.wav", (np.clip(clip, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"{path.name}: {len(audio) / SR / 60:.1f} min, {len(pieces)} pieces between breaks, "
          f"{len(chosen)} matched to items")
    return sorted(chosen)


def load_audio(path):
    """Any common audio file as mono float32 at 16 kHz."""
    from faster_whisper import decode_audio
    return decode_audio(str(path), sampling_rate=SR)


def cmd_import(args):
    """Recordings -> <out>/items/<code>.wav (16 kHz mono), with any <code>.dragon.txt."""
    import numpy as np
    items = load_set(args.set)
    codes = {it["id"] for it in items}
    (args.out / "items").mkdir(parents=True, exist_ok=True)
    taken, long_files = [], []
    for path in sorted(getattr(args, "from").rglob("*")):
        if not path.is_file():
            continue
        code = path.name.split(".")[0].strip().lower()
        if path.suffix.lower() in AUDIO:
            if code not in codes:
                long_files.append(path)                 # not an item code: one long recording to cut up
                continue
            audio = load_audio(path)
            save_wav(args.out / "items" / f"{code}.wav", (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
            taken.append(code)
        elif path.name.lower().endswith(".dragon.txt") and code in codes:
            (args.out / "items" / f"{code}.dragon.txt").write_text(path.read_text(encoding="utf-8-sig"), encoding="utf-8")
    if long_files:
        import dictation_reliability as dr
        engine = dr.make_engine("whisper", args.model)
        for path in long_files:                         # later files win, like later readings
            taken += split_recording(path, items, args.out, engine)
    print(f"{len(set(taken))} of {len(codes)} items imported into {args.out}")
    missing = sorted(codes - set(taken))
    if missing:
        print("still missing:", " ".join(missing))


# ── score ────────────────────────────────────────────────────────────────────
# Spellings that are the same word. The plain count charges these as errors; the
# adjusted count does not. Found by reading every flagged difference on the set.
_SAME_WORD = {"colour": "color", "colours": "color", "colors": "color", "okay": "ok", "litre": "liter",
              "litres": "liters", "grey": "gray", "diarrhoea": "diarrhea", "haemoglobin": "hemoglobin",
              "anaemia": "anemia", "oesophagus": "esophagus", "paediatric": "pediatric", "tumour": "tumor",
              "centre": "center", "metre": "meter", "fibre": "fiber", "labour": "labor",
              "behaviour": "behavior", "odour": "odor", "oedema": "edema", "foetal": "fetal",
              "1st": "first", "2nd": "second", "3rd": "third"}


def _canonical(word: str) -> str:
    word = _SAME_WORD.get(word, word)
    for british, american in (("isation", "ization"), ("ised", "ized"), ("ising", "izing"), ("ise", "ize"),
                              ("yse", "yze")):
        if word.endswith(british) and len(word) > len(british) + 3:
            return word[:-len(british)] + american
    return word


def _join_compounds(words: list, other: list) -> list:
    """Write "long standing" as "longstanding" when the other side has it as one word."""
    whole, out, i = set(other), [], 0
    while i < len(words):
        if i + 1 < len(words) and words[i] + words[i + 1] in whole and words[i] not in whole:
            out.append(words[i] + words[i + 1])
            i += 2
        else:
            out.append(words[i])
            i += 1
    return out


def adjusted_errors(reference: str, text: str) -> int:
    """
    Word errors after forgiving what is not a recognition mistake: British and
    American spellings, ok/okay, and one word written as two or two as one
    ("follow up" / "followup", "breast bone" / "breastbone").
    """
    import dictation_reliability as dr
    ref = [_canonical(w) for w in dr.normalize_words(reference)]
    hyp = [_canonical(w) for w in dr.normalize_words(text)]
    ref, hyp = _join_compounds(ref, hyp), _join_compounds(hyp, ref)
    return sum(op != "ok" for op, _i, _j in dr.align(ref, hyp))


PROFILES = {"whisper": "candidate_full", "whisper-personal": "personal", "whisper-topics": "personal_topics", "medasr": "classic_full", "parakeet": "classic_full", "canary": "classic_full"}


def transcribe_all_language(items: list, out: Path, model=None) -> dict:
    """{id: text} for a Spanish / French / Swahili set: Whisper with that language's pack and all options."""
    import dictation_reliability as dr
    import engines
    import lang_commands
    import lang_packs
    import pause_flow
    from bench_engine import load_wav

    pack = lang_packs.get(items[0]["language"])
    cache = out / "local_whisper.json"
    done = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else {}
    todo = [it for it in items if it["id"] not in done and (out / "items" / f"{it['id']}.wav").is_file()]
    if not todo:
        return done
    tuned = model or engines.tuned_model(pack.code)
    engine = dr.make_engine("whisper", str(tuned) if tuned else None)
    engine.language = pack.code
    pause_flow.set_language(pack)
    post = lang_commands.corrector_for(pack)
    if post is not None:
        post.same_sound = True
    prompt = lang_commands.prompt_for(pack, True)
    for it in todo:
        audio = load_wav(out / "items" / f"{it['id']}.wav")
        raw = dr.run_pipeline(engine, audio, None, prompt, None, post, dr.PROFILES["candidate"], with_spoken=True)[4]
        done[it["id"]] = lang_commands.apply(lang_commands.format_readings(raw, pack), pack, punctuation=True)
        cache.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  whisper {it['id']}", flush=True)
    return done


def score_language(args, items: list, systems: dict):
    """Word errors, marks and layout for a non-English set (any alphabet)."""
    import lang_reliability as lr
    result, table = {"items": len(items), "language": items[0]["language"], "systems": {}}, []
    print(f"\n{len(items)} items in {items[0]['language']} scored against the text that was read")
    print(f"{'system':10s} {'kind':8s} {'n':>3s} {'WER %':>7s} {'marks missing':>14s} {'marks added':>12s} {'layout ok':>10s}")
    for name, texts in systems.items():
        rows = []
        for it in items:
            text = texts.get(it["id"], "")
            ref, hyp = lr.word_tokens(it["reference"]), lr.word_tokens(text)
            marks, missing, added = lr.mark_errors(it["reference"], text)
            rows.append({"id": it["id"], "category": it["category"], "ref_words": len(ref),
                         "errors": lr.edit_distance(ref, hyp), "marks": marks, "marks_missing": missing,
                         "marks_added": added, "format_ok": lr.layout(it["reference"]) == lr.layout(text), "text": text})
        result["systems"][name] = {"rows": rows}
        for kind in ("short", "consult", "all"):
            sel = [r for r in rows if kind == "all" or r["category"] == kind]
            if sel:
                words = max(1, sum(r["ref_words"] for r in sel))
                print(f"{name:10s} {kind:8s} {len(sel):3d} {100 * sum(r['errors'] for r in sel) / words:7.2f} "
                      f"{sum(r['marks_missing'] for r in sel):>7d}/{sum(r['marks'] for r in sel):<6d} "
                      f"{sum(r['marks_added'] for r in sel):>12d} {sum(r['format_ok'] for r in sel):>7d}/{len(sel)}")
        table += [{"system": name, "id": r["id"], "kind": r["category"], "ref_words": r["ref_words"],
                   "errors": r["errors"], "marks_missing": r["marks_missing"], "marks_added": r["marks_added"],
                   "format_ok": r["format_ok"]} for r in rows]
    (args.out / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    with (args.out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    print(f"\nresults: {args.out / 'results.json'} and results.csv")


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
    if model and engine_name.startswith("whisper"):
        import os
        os.environ["MYTRANSCRIBE_MODEL"] = str(model)
    engine = engines.build(engine_name.split("-")[0])
    profile = dr.PROFILES[PROFILES[engine_name]]
    style = dr.style_for(profile)
    builder, post = dr.build_text_pipeline(style, count=getattr(engine, "count_tokens", None), env=profile.get("env", {}))
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

    items = [it for it in load_set(args.set) if (args.out / "items" / f"{it['id']}.wav").is_file()]
    if not items:
        raise SystemExit(f"no recorded items in {args.out}; run 'record' or 'import' first")
    dragon = {it["id"]: (args.out / "items" / f"{it['id']}.dragon.txt").read_text(encoding="utf-8")
              for it in items if (args.out / "items" / f"{it['id']}.dragon.txt").is_file()}
    systems = {"dragon": dragon} if dragon else {}         # recordings made without Dragon have no Dragon text
    if dragon and len(dragon) < len(items):
        print(f"note: Dragon text exists for {len(dragon)} of {len(items)} items; its totals cover only those")
        items_dragon = [it for it in items if it["id"] in dragon]
    else:
        items_dragon = items
    if items[0]["language"] != "en":                      # only Whisper understands the other languages
        print(f"running whisper ({items[0]['language']}) on {len(items)} recordings ...", flush=True)
        systems["whisper"] = transcribe_all_language(items, args.out, args.model)
        return score_language(args, items, systems)
    for name in args.engines.split(","):
        ok, why = engines.availability(name.split("-")[0])
        if not ok:
            print(f"skipping {name}: {why}")
            continue
        print(f"running {name} on {len(items)} recordings ...", flush=True)
        systems[name] = transcribe_all(name, items, args.out, args.model)

    result, table = {"items": len(items), "systems": {}}, []
    for name, texts in systems.items():
        scored = items_dragon if name == "dragon" else items
        rows = [dr.score_row({"id": it["id"], "split": "validation", "category": it["category"],
                              "reference": it["reference"], "spoken": it["spoken"]},
                             "orig", texts.get(it["id"], ""), texts.get(it["id"], ""), audio_s=0.0)
                for it in scored]
        for it, r in zip(scored, rows):
            r["errors_adjusted"] = adjusted_errors(it["reference"], texts.get(it["id"], ""))
        by_kind = {}
        for kind in ("short", "consult", "all"):
            sel = [r for r in rows if kind == "all" or r["category"] == kind]
            if sel:
                by_kind[kind] = dr.summarise(sel, ["orig"])["orig"]
                words = sum(r["ref_words"] for r in sel)
                by_kind[kind]["wer_adjusted"] = round(100 * sum(r["errors_adjusted"] for r in sel) / max(1, words), 2)
        result["systems"][name] = {"summary": by_kind, "rows": rows}
        for r in rows:
            table.append({"system": name, "id": r["id"], "kind": r["category"], "ref_words": r["ref_words"],
                          "errors": r["errors"], "errors_adjusted": r["errors_adjusted"],
                          "format_ok": r["format_ok"], "tail_ok": r["tail_ok"]})
    (args.out / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    with (args.out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)

    print(f"\n{len(items)} items scored against the text that was read (word errors ignore punctuation marks)")
    print("adjusted = not counting spelling variants (colour/color, ok/okay) or one word written as two")
    print(f"{'system':10s} {'kind':8s} {'n':>3s} {'WER %':>7s} {'adjusted':>9s} {'format ok':>10s} {'commands':>10s} "
          f"{'last words':>11s}")
    for name, data in result["systems"].items():
        for kind, s in data["summary"].items():
            print(f"{name:10s} {kind:8s} {s['recordings']:3d} {s['wer']:7.2f} {s['wer_adjusted']:9.2f} {s['format']:>10s} "
                  f"{s['commands']:>10s} {s['tail']:>11s}")
    print(f"\nresults: {args.out / 'results.json'} and results.csv")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, func in (("show", cmd_show), ("record", cmd_record), ("score", cmd_score), ("import", cmd_import)):
        p = sub.add_parser(name)
        p.add_argument("--set", type=Path, default=DEFAULT_SET)
        p.set_defaults(func=func)
        if name != "show":
            p.add_argument("--out", required=True, type=Path)
        if name == "import":
            p.add_argument("--from", required=True, type=Path, help="folder holding the recordings")
            p.add_argument("--model", help="local Whisper model folder (used to find the breaks)")
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

"""
synth_voices.py — read the synthetic voice set aloud with OpenAI's voices, for testing.

Each voice in the panel (validation/synthetic_voices_en_v1.json) reads every script
in the set (validation/synthetic_set_en_v1.txt) the way its style dictates
(src/tuning/sets.py), saying "period" or "full stop" as the voice's accent would.
Units are spelled out for the voice ("500 milligrams"); the written text keeps them.

    synth_voices.py plan   [--voices V01,V02] [--items e01,s04]   # no network, no cost
    synth_voices.py make --go [--voices ...] [--items ...] [--budget-usd 5]
    synth_voices.py status

The audio is AI-generated, for testing and tuning only: never for training, never
published (docs/testing/README.md, terms read 2026-11-18). It stays under the ignored
results_1060/ tree with a manifest of the engine, model, voice, instruction and date.

The key is read from a file encrypted for this Windows account (DPAPI), made with
Read-Host -AsSecureString | ConvertFrom-SecureString, or from OPENAI_API_KEY. It is
never printed or written anywhere else.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from tuning import sets  # noqa: E402

PANEL = ROOT / "validation" / "synthetic_voices_en_v1.json"
OUT = ROOT / "results_1060" / "synthetic_voices" / "en_v1"
KEY_FILE = ROOT / "results_1060" / "synthetic_voices" / "secrets" / "openai.dpapi"
URL = "https://api.openai.com/v1/audio/speech"
SOURCE_RATE, RATE = 24000, 16000       # OpenAI "pcm" is 24 kHz 16-bit mono; the app hears 16 kHz
MAX_INPUT = 4096                       # characters per request
USD_PER_MINUTE = 0.015                 # OpenAI's published estimate for gpt-4o-mini-tts (not verified)
WORDS_PER_MINUTE = 140                 # for the estimate before anything is made

PACE = {"slow": "slightly slow and deliberate", "normal": "steady and conversational",
        "fast": "brisk, like a busy clinician"}
# Units as a voice should say them, after a number. Longest first.
_UNITS = [("mmol/L", "millimoles per litre"), ("g/L", "grams per litre"), ("mcg", "micrograms"),
          ("mg", "milligrams"), ("kg", "kilograms"), ("cm", "centimetres"), ("L", "litres"), ("g", "grams")]
_UNIT = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s?(" + "|".join(re.escape(u) for u, _ in _UNITS) + r")(?![\w/])")


# ── What each voice says ─────────────────────────────────────────────────────
def load_panel(path: Path = PANEL) -> dict:
    panel = json.loads(path.read_text(encoding="utf-8"))
    ids = [v["id"] for v in panel["voices"]]
    if len(set(ids)) != len(ids):
        raise ValueError("voice ids must be unique")
    for v in panel["voices"]:
        if v["stop"] not in sets.STOP_WORDS or v["pace"] not in PACE or v["split"] not in ("dev", "held"):
            raise ValueError(f"{v['id']}: bad stop, pace or split")
    return panel


# A dictator pauses briefly after each spoken command; a mark after it makes the voice do so.
_PAUSE_AFTER = [(re.compile(r"\b(period|full stop|question mark|new line|new paragraph)\b(?![.,?])"), r"\1."),
                (re.compile(r"\b(comma|colon|semicolon|open quote|close quote)\b(?![.,?])"), r"\1,")]


def voice_text(spoken: str, mode: str = "every") -> str:
    """The dictated words as the voice should say them: units and minus signs spelled out,
    and a short pause after each spoken command."""
    names = dict(_UNITS)

    def unit(m):
        word = names[m.group(2)]
        if m.group(1) in ("1", "-1") and word.endswith("s") and "per" not in word:
            word = word[:-1]
        return f"{m.group(1)} {word}"
    text = _UNIT.sub(unit, spoken)
    text = re.sub(r"(?<![\w.])-(\d)", r"minus \1", text)
    if mode != "natural":
        for pattern, repl in _PAUSE_AFTER:
            text = pattern.sub(repl, text)
    return text


def instructions(voice: dict, style: str) -> str:
    natural = style == "natural"
    return (f"Voice: a physician dictating into speech recognition software. "
            f"Accent: {voice['accent']}, natural and mild, never exaggerated. Pace: {PACE[voice['pace']]}. "
            f"Read the text exactly as written, word for word. "
            + ("Speak naturally, with a short pause at each blank line. " if natural else
               f"Words such as 'comma', '{voice['stop']}', 'colon', 'new line' and 'new paragraph' are "
               f"commands to the software: say them plainly as words. ")
            + "Do not add, skip or change any word. Say drug names and abbreviations as a clinician would.")


def plan(panel: dict, voices=None, items=None) -> list:
    """Every clip to make: one per voice and script, with the exact text and instruction."""
    script_set = sets.load_set(ROOT / "validation" / panel["set"])
    chosen_v = [v for v in panel["voices"] if not voices or v["id"] in voices]
    chosen_i = [i for i in script_set if not items or i["id"] in items]
    clips = []
    for v in chosen_v:
        for it in chosen_i:
            mode = sets.mode_of(it)
            said = sets.spoken_form(it["said"], language=panel["language"], mode=mode, stop=v["stop"])
            text = voice_text(said, mode)
            if len(text) > MAX_INPUT:
                raise ValueError(f"{it['id']}: {len(text)} characters, more than one request takes")
            clips.append({"voice_id": v["id"], "voice": v["voice"], "accent": v["accent"], "split": v["split"],
                          "item": it["id"], "style": it["style"], "item_split": it["split"], "stop": v["stop"],
                          "spoken": said, "input": text, "instructions": instructions(v, it["style"])})
    return clips


def estimate(clips: list) -> tuple:
    minutes = sum(len(c["input"].split()) for c in clips) / WORDS_PER_MINUTE
    return minutes, minutes * USD_PER_MINUTE


# ── Audio ────────────────────────────────────────────────────────────────────
def resample(x: np.ndarray, src: int = SOURCE_RATE, dst: int = RATE) -> np.ndarray:
    """Band-limited resampling by FFT, with a little silence padded so the ends do not wrap."""
    pad = src // 10
    y = np.concatenate([np.zeros(pad), x.astype(np.float64), np.zeros(pad)])
    n_out = int(round(len(y) * dst / src))
    spec = np.fft.rfft(y)[: n_out // 2 + 1]
    out = np.fft.irfft(spec, n_out) * (n_out / len(y))
    trim = int(round(pad * dst / src))
    return out[trim: len(out) - trim]


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    pcm = np.clip(np.round(samples), -32768, 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


# ── Key and request ──────────────────────────────────────────────────────────
def _dpapi_decrypt(blob: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(blob, len(blob))
    src, out = Blob(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("the saved key could not be decrypted on this Windows account")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def read_key(key_file: Path = KEY_FILE) -> str:
    if key_file.is_file():
        hexed = key_file.read_text(encoding="utf-8-sig").strip()
        return _dpapi_decrypt(bytes.fromhex(hexed)).decode("utf-16-le").strip()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise SystemExit(f"No key: save one to {key_file} (see docs/testing/SYNTHETIC_VOICES.md)")
    return key


def _post(body: dict, key: str, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def speak(clip: dict, model: str, key: str, post=_post) -> bytes:
    """Raw 24 kHz PCM for one clip, retrying on rate limits and server errors."""
    body = {"model": model, "voice": clip["voice"], "input": clip["input"],
            "instructions": clip["instructions"], "response_format": "pcm"}
    for attempt in range(4):
        try:
            return post(body, key)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SystemExit(f"OpenAI refused the key ({exc.code}); nothing more will be sent")
            if exc.code not in (429, 500, 502, 503) or attempt == 3:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 * 3 ** attempt)
    raise RuntimeError("unreachable")


# ── Commands ─────────────────────────────────────────────────────────────────
def done_clips(out: Path) -> set:
    manifest = out / "manifest.jsonl"
    if not manifest.is_file():
        return set()
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["voice_id"], r["item"]) for r in rows if (out / r["wav"]).is_file()}


README = """AI-generated speech (OpenAI {model}) reading fictional scripts.
For testing and tuning MyTranscribe only: never for training a model, never published.
Terms read {terms}; see docs/testing/README.md in the repository.
"""


def cmd_plan(args, panel):
    clips = plan(panel, args.voices, args.items)
    minutes, usd = estimate(clips)
    todo = [c for c in clips if (c["voice_id"], c["item"]) not in done_clips(args.out)]
    print(f"{len(clips)} clips ({len(todo)} not made yet), about {minutes:.0f} minutes of speech, "
          f"about ${usd:.2f} at OpenAI's estimate of ${USD_PER_MINUTE}/minute")
    for c in clips[: args.show]:
        print(f"\n[{c['voice_id']} {c['voice']} / {c['item']} {c['style']}]\n{c['input']}")
    return clips


def cmd_make(args, panel, post=None):
    post = post or _post                       # looked up now, so a test's stand-in is used
    if not args.go:
        raise SystemExit("make spends money: add --go (run 'plan' first to see the cost)")
    clips = [c for c in plan(panel, args.voices, args.items) if (c["voice_id"], c["item"]) not in done_clips(args.out)]
    minutes, usd = estimate(clips)
    if usd > args.budget_usd:
        raise SystemExit(f"estimated ${usd:.2f} is over --budget-usd {args.budget_usd}; choose fewer voices or items")
    key = read_key(args.key_file)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "README.txt").write_text(README.format(model=panel["model"], terms=panel["terms_read"]),
                                         encoding="utf-8")
    lock, spent = threading.Lock(), {"seconds": 0.0, "clips": 0}

    def one(clip):
        if spent["seconds"] / 60 * USD_PER_MINUTE > args.budget_usd:
            return
        pcm = np.frombuffer(speak(clip, panel["model"], key, post), dtype="<i2").astype(np.float64)
        rel = Path(clip["voice_id"]) / f"{clip['item']}.wav"
        write_wav(args.out / clip["voice_id"] / f"{clip['item']}.24k.wav", pcm, SOURCE_RATE)
        write_wav(args.out / rel, resample(pcm), RATE)
        seconds = len(pcm) / SOURCE_RATE
        row = dict(clip, wav=str(rel).replace("\\", "/"), seconds=round(seconds, 2), engine=panel["engine"],
                   model=panel["model"], rate=RATE, source_rate=SOURCE_RATE, ai_generated=True,
                   sha256=hashlib.sha256(pcm.astype("<i2").tobytes()).hexdigest(),
                   made=dt.datetime.now().isoformat(timespec="seconds"), terms_read=panel["terms_read"])
        with lock:
            with open(args.out / "manifest.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            spent["seconds"] += seconds
            spent["clips"] += 1
            print(f"{spent['clips']}/{len(clips)} {clip['voice_id']} {clip['item']} {seconds:.1f} s", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in [pool.submit(one, c) for c in clips]:
            future.result()
    print(f"made {spent['clips']} clips, {spent['seconds'] / 60:.1f} minutes, "
          f"about ${spent['seconds'] / 60 * USD_PER_MINUTE:.2f}")


def cmd_status(args, panel):
    done = done_clips(args.out)
    for v in panel["voices"]:
        n = sum(1 for vid, _ in done if vid == v["id"])
        print(f"{v['id']} {v['voice']:8s} {v['accent']:45s} {n} clips")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("plan", "make", "status"))
    ap.add_argument("--panel", type=Path, default=PANEL)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--key-file", type=Path, default=KEY_FILE)
    ap.add_argument("--voices", type=lambda s: s.split(","), help="voice ids, e.g. V01,V04")
    ap.add_argument("--items", type=lambda s: s.split(","), help="script ids, e.g. e01,n02")
    ap.add_argument("--go", action="store_true", help="make: actually call the API (costs money)")
    ap.add_argument("--budget-usd", type=float, default=5.0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--show", type=int, default=2, help="plan: how many scripts to print")
    args = ap.parse_args(argv)
    panel = load_panel(args.panel)
    {"plan": cmd_plan, "make": cmd_make, "status": cmd_status}[args.command](args, panel)


if __name__ == "__main__":
    main()

"""
record_snippets.py — record yourself reading the fictional test snippets, for scoring.

Shows each snippet's text; press Enter to start recording, Enter again to stop
(r + Enter redoes the last one, q + Enter quits early). Saves 16 kHz mono WAVs and a
manifest.json that eval_snippets.py can score, so real-mic results line up with the
synthetic ones. Only fictional text is read; recordings stay in the (gitignored)
output folder. Delete them when you're done if you like.

    venv1060\\Scripts\\python.exe scripts\\record_snippets.py --out results_1060\\real_headset
    venv1060\\Scripts\\python.exe scripts\\eval_snippets.py --manifest results_1060\\real_headset\\manifest.json ^
        --settings large-v3:b1,large-v3-turbo:b1 --show-text

    --list-devices     show microphones;  --device N  use one other than the default
    --only message,exam   record just some categories
    --redo 6           re-record snippet 06 only (keeps everything else already recorded)
"""

import argparse
import json
import sys
import threading
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from make_snippets import SNIPPETS   # noqa: E402

SR = 16000
FRAMES = 1024


def list_devices(pa):
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if d.get("maxInputChannels", 0) > 0:
            print(f"  {i}: {d['name']}")


def record_until_enter(mic):
    """Record until the user presses Enter; returns int16 PCM bytes.

    Uses the app's ReadyMic (device kept open, 0.5 s pre-roll), so recordings
    behave like the app: no clipped first word on Bluetooth headsets.
    """
    session, _ = mic.session()
    frames, stop = [], threading.Event()

    def loop():
        while not stop.is_set():
            try:
                frames.append(session.read(FRAMES))
            except OSError:
                break
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    input("   ● recording… press Enter to stop ")
    stop.set()
    t.join(timeout=2)
    session.close()
    return b"".join(frames)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "results_1060" / "real_headset")
    ap.add_argument("--device", type=int)
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--only", help="comma list of categories: message,result,exam")
    ap.add_argument("--profile", default="real", help="label stored in the manifest")
    ap.add_argument("--redo", help="comma list of snippet numbers to (re)record, e.g. 6 or 6,12 "
                                   "(the number in the file name, 00-26)")
    args = ap.parse_args(argv)

    import pyaudio
    sys.path.insert(0, str(ROOT / "src"))
    from mic_ready import ReadyMic
    pa = pyaudio.PyAudio()
    mic = None
    try:
        if args.list_devices:
            list_devices(pa)
            return 0

        def open_stream():
            return pa.open(format=pyaudio.paInt16, channels=1, rate=SR, input=True,
                           frames_per_buffer=FRAMES, input_device_index=args.device), None
        mic = ReadyMic(open_stream=open_stream)
        mic.start()
        keep = set(args.only.split(",")) if args.only else None
        redo = {int(n) for n in args.redo.split(",")} if args.redo else None
        items = [(i, s) for i, s in enumerate(SNIPPETS)
                 if (keep is None or s[0] in keep) and (redo is None or i in redo)]
        args.out.mkdir(parents=True, exist_ok=True)
        mpath = args.out / "manifest.json"
        manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else []   # add to earlier runs
        k = 0
        print(f"{len(items)} snippets. Read each one naturally, including commands like "
              f"'new line'.\nSay abbreviations the way you normally would (e.g. 'S N T').\n")
        while k < len(items):
            i, (cat, spoken, written, terms) = items[k]
            print(f"[{k + 1}/{len(items)}] ({cat})  {spoken}")
            cmd = input("   Enter = start, q = quit: ").strip().lower()
            if cmd == "q":
                break
            pcm = record_until_enter(mic)
            name = f"{i:02d}_{cat}__{args.profile}.wav"
            with wave.open(str(args.out / name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(pcm)
            secs = len(pcm) / 2 / SR
            if input(f"   saved {secs:.1f}s. Enter = next, r = redo: ").strip().lower() == "r":
                continue
            manifest = [m for m in manifest if m["audio"] != name]
            manifest.append({"audio": name, "scenario": f"{i:02d}_{cat}", "category": cat,
                             "profile": args.profile, "spoken": spoken, "reference": written,
                             "terms": terms, "seconds": round(secs, 1)})
            manifest.sort(key=lambda m: m["audio"])
            mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
            k += 1
        print(f"\n{len(manifest)} recordings in {args.out}. Score them with eval_snippets.py (see --help).")
    finally:
        if mic is not None:
            mic.stop()
        pa.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())

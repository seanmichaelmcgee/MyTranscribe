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

    --script docs/samples/personal_v1.json   read a frozen fictional sample set
    Custom sets resume saved clips unless --redo is specified. Use a separate
    --out and --profile for each microphone / normal-voice / whispered condition.
"""

import argparse
import json
import re
import sys
import threading
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from make_snippets import SNIPPETS   # noqa: E402
from asr_trial_common import local_result_path, sha256, write_json   # noqa: E402

SR = 16000
FRAMES = 1024


def load_samples(path=None):
    """Read sample data only; never execute a supplied script or generate hints."""
    if path is None:
        return [dict(scenario=f"{i:02d}_{cat}", category=cat, spoken=spoken,
                     reference=written, terms=terms)
                for i, (cat, spoken, written, terms) in enumerate(SNIPPETS)]
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Sample script must be a nonempty JSON list")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each sample must be an object")
        scenario = row.get("scenario", "")
        if not isinstance(scenario, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", scenario):
            raise ValueError("Sample scenario must be a simple unique identifier")
        if scenario in seen:
            raise ValueError("Duplicate sample scenario: " + scenario)
        seen.add(scenario)
        if row.get("category") not in {"message", "result", "exam", "letter"}:
            raise ValueError("Unknown sample category")
        if any(not isinstance(row.get(k), str) or not row[k].strip()
               for k in ("spoken", "reference")):
            raise ValueError("Each sample needs spoken text and a written reference")
        for key in ("terms", "names"):
            values = row.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(key + " must be a list of nonempty strings")
        if row.get("split", "calibration") not in {"calibration", "holdout"}:
            raise ValueError("Unknown sample split")
    return rows


def select_samples(rows, manifest, out, profile, keep=None, redo=None, resume=False):
    """Keep stable script indices; custom sets skip only files actually saved."""
    saved = {row["audio"] for row in manifest}
    items = []
    for i, row in enumerate(rows):
        if keep is not None and row["category"] not in keep:
            continue
        if redo is not None and i not in redo:
            continue
        name = f"{row['scenario']}__{profile}.wav"
        if resume and redo is None and name in saved and (out / name).is_file():
            continue
        items.append((i, row))
    return items


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
    ap.add_argument("--script", type=Path, help="JSON sample data with frozen spoken/written references")
    ap.add_argument("--only", help="comma list of categories: message,result,exam,letter")
    ap.add_argument("--profile", default="real", help="label stored in the manifest")
    ap.add_argument("--redo", help="comma list of snippet numbers to (re)record, e.g. 6 or 6,12 "
                                   "(the zero-based script index shown before the text)")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.profile):
        ap.error("--profile must contain only letters, numbers, underscores or hyphens")
    rows = load_samples(args.script)
    script_hash = sha256(args.script) if args.script else None
    args.out = local_result_path(args.out)
    mpath = args.out / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else []
    if script_hash and any(m.get("sample_script_sha256") != script_hash for m in manifest):
        ap.error("This output folder contains a different sample set; choose a fresh --out")
    keep = set(args.only.split(",")) if args.only else None
    redo = {int(n) for n in args.redo.split(",")} if args.redo else None
    items = select_samples(rows, manifest, args.out, args.profile, keep, redo,
                           resume=args.script is not None)

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
        if not items:
            print("No clips pending. Use --redo INDEX to replace a saved recording.")
            return 0
        mic = ReadyMic(open_stream=open_stream)
        mic.start()
        args.out.mkdir(parents=True, exist_ok=True)
        k = 0
        print(f"{len(items)} snippets. Read each one naturally, including commands like "
              f"'new line'.\nSay abbreviations the way you normally would (e.g. 'S N T').\n")
        while k < len(items):
            i, sample = items[k]
            cat, spoken, written = (sample[key] for key in ("category", "spoken", "reference"))
            print(f"[{i:02d}] ({cat})  {spoken}")
            cmd = input("   Enter = start, q = quit: ").strip().lower()
            if cmd == "q":
                break
            pcm = record_until_enter(mic)
            name = f"{sample['scenario']}__{args.profile}.wav"
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
                             "terms": sample.get("terms", []), "seconds": round(secs, 1),
                             **({"scenario": sample["scenario"], "names": sample.get("names", []),
                                 "split": sample.get("split", "calibration"),
                                 "sample_script_sha256": script_hash} if script_hash else {})})
            manifest.sort(key=lambda m: m["audio"])
            write_json(mpath, manifest)
            k += 1
        print(f"\n{len(manifest)} recordings in {args.out}. Score them with eval_snippets.py (see --help).")
    finally:
        if mic is not None:
            mic.stop()
        pa.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())

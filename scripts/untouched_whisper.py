"""
How much the app adds to Whisper large-v3 as it comes.

Runs the same model files and number format as the app, but straight through
faster-whisper with its own defaults (beam 5, its own 30 s windows, previous
text carried, no prompt, no voice-activity filter, language English) and none
of the app's text handling. The app's text steps are then added one at a time
to that same raw text, without new recognition:

  untouched   the raw Whisper text
  + commands  spoken punctuation and commands turned into marks and layout
  + clean-up  medical clean-up: readings, units, spoken numbers, drug names

The app's own build (medical prompt, pause-aware windows, term correction and
every text option) is the last row: saved from the Corti run, re-run here on
the held-out recordings.

    untouched_whisper.py corti --audio results_1060/corti/audio --out results_1060/untouched
    untouched_whisper.py held  --heldout-root <results_1060 with the held-out manifests> --out results_1060/untouched

Corti: evaluation only, run once; score with corti_benchmark.py score. Local, no network.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import dictation_reliability as dr                                      # noqa: E402
import text_fixes                                                       # noqa: E402
import voice_commands                                                   # noqa: E402

STEPS = ("untouched", "commands", "cleanup")


def steps(raw: str) -> dict:
    marks = voice_commands.apply(raw, lenient=True, punctuation=True)
    return {"untouched": raw, "commands": marks,
            "cleanup": voice_commands.apply(text_fixes.format_readings(raw), lenient=True, punctuation=True)}


def untouched(engine, audio) -> str:
    segments, _ = engine.model.transcribe(audio, language="en", beam_size=5)
    return " ".join(s.text.strip() for s in segments).strip()


def cmd_corti(args, engine):
    from corti_benchmark import load_wav
    rows, t0 = {s: [] for s in STEPS}, time.perf_counter()
    for wav in sorted(args.audio.glob("row*.wav")):
        audio = load_wav(wav)
        raw = untouched(engine, audio)
        for name, text in steps(raw).items():
            rows[name].append({"row_index": int(wav.stem[3:]), "spoken": raw, "formatted": text})
        print(f"{wav.stem} done ({time.perf_counter() - t0:.0f}s)", flush=True)
    out = args.out / "corti"
    out.mkdir(parents=True, exist_ok=True)
    for name, r in rows.items():
        (out / f"{name}.json").write_text(json.dumps({"profile": name, "rows": r}, indent=1, ensure_ascii=False),
                                          encoding="utf-8")


def cmd_held(args, engine):
    profile = dr.PROFILES["candidate_full"]
    style = dr.style_for(profile)
    builder, post = dr.build_text_pipeline(style, count=getattr(engine, "count_tokens", None))
    items = dr.load_corpus(args.heldout_root, "held")
    errors = {s: 0 for s in STEPS + ("app",)}
    words, rows = 0, []
    for e in items:
        audio = dr.load_wav(e["wav"])
        raw = untouched(engine, audio)
        texts = steps(raw)
        texts["app"] = dr.run_pipeline(engine, audio, None, style, builder, post, profile)[0]
        n = len(dr.normalize_words(e["reference"]))
        words += n
        row = {"id": e["id"], "ref_words": n}
        for name, text in texts.items():
            k = dr.word_edits(e["reference"], text)
            errors[name] += k
            row[name] = {"errors": k, "format_ok": dr.format_ok(e["reference"], text), "text": text}
        rows.append(row)
        print(f"{e['id'][:40]:40s} " + " ".join(f"{s} {row[s]['errors']:3d}" for s in errors), flush=True)
    fmt = [r for r, e in zip(rows, items) if dr.structure(e["reference"])]
    summary = {s: {"wer": round(100 * errors[s] / words, 2),
                   "format": f"{sum(r[s]['format_ok'] for r in fmt)}/{len(fmt)}"} for s in errors}
    summary["recordings"], summary["words"] = len(items), words
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "held.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False),
                                        encoding="utf-8")
    print(json.dumps(summary, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("corti")
    c.add_argument("--audio", required=True, type=Path)
    c.add_argument("--out", required=True, type=Path)
    h = sub.add_parser("held")
    h.add_argument("--heldout-root", required=True, type=Path)
    h.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    engine = dr.make_engine("whisper")
    print(f"model {engine.config.model}, {engine.config.compute_type} on {engine.config.device}", flush=True)
    (cmd_corti if args.cmd == "corti" else cmd_held)(args, engine)


if __name__ == "__main__":
    main()

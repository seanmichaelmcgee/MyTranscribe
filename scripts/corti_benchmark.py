"""
Benchmark the app pipeline on Corti Med-Dictate (English, 24 notes).

Evaluation only: the dataset licence allows benchmarking existing systems and
forbids using it to develop them, so run a finished build once and do not tune
against the result. Audio, references and outputs stay in the ignored
results_1060/ tree. Nothing from the references reaches recognition.

    corti_benchmark.py run   --audio <dir of rowNN.wav> --out <dir> --profile candidate
    corti_benchmark.py score --references references.json --metrics report_metrics_v1.py --out <dir>

"score" uses the metric module frozen for the October benchmark so numbers are
comparable: the spoken track is scored on the text before spoken commands are
converted, the formatted track on the final text. Any <name>.json in --out with
{"rows": [{"row_index", "spoken", "formatted"}]} is scored, so saved texts from
other systems can sit beside the local profiles.
"""

import argparse
import importlib.util
import json
import time
import wave
from pathlib import Path

import numpy as np

VIEWS = (("spoken", "transcription", "conservative"), ("formatted", "transcription_formatted", "conservative"),
         ("formatted", "transcription_formatted", "written_numeric_equivalence"))


def load_wav(path):
    with wave.open(str(path)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2), path
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768


def cmd_run(args):
    import dictation_reliability as dr

    profile = dr.PROFILES[args.profile]
    engine = dr.make_engine(args.engine, args.model, profile)
    cfg = engine.config
    style = dr.style_for(profile)
    builder, post = dr.build_text_pipeline(style, count=getattr(engine, "count_tokens", None), env=profile.get("env", {}))
    tag = args.profile if args.engine == "whisper" else f"{args.engine}_{args.profile}"
    rows, t0 = [], time.perf_counter()
    for wav in sorted(args.audio.glob("row*.wav")):
        audio = load_wav(wav)
        final, _, elapsed, rescued, spoken = dr.run_pipeline(engine, audio, None, style, builder, post, profile,
                                                             with_spoken=True)
        rows.append({"row_index": int(wav.stem[3:]), "audio_s": round(len(audio) / 16000, 2),
                     "elapsed_s": round(elapsed, 2), "rescued": rescued, "spoken": spoken, "formatted": final})
        print(f"{wav.stem} done ({time.perf_counter() - t0:.0f}s)", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{tag}.json").write_text(json.dumps(
        {"profile": tag, "model": str(cfg.model), "compute_type": engine.config.compute_type,
         "device": engine.config.device, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")


def score_rows(metrics, refs, rows):
    """{(track, view): {S, D, I, N}} summed over rows, plus the same per row."""
    totals, per_row = {}, {}
    for r in rows:
        ref = refs[r["row_index"]]
        for track, field, view in VIEWS:
            counts, _ = metrics(ref[field], r[track], view)
            per_row[(r["row_index"], track, view)] = counts
            t = totals.setdefault((track, view), dict.fromkeys("SDIN", 0))
            for k in "SDIN":
                t[k] += counts[k]
    return totals, per_row


def cmd_score(args):
    spec = importlib.util.spec_from_file_location("frozen_metrics", args.metrics)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    refs = {r["row_index"]: r for r in json.loads(args.references.read_text(encoding="utf-8-sig"))}
    runs = {p.stem: json.loads(p.read_text(encoding="utf-8"))["rows"] for p in sorted(args.out.glob("*.json"))
            if p.stem != "scores"}
    common = set.intersection(*(set(r["row_index"] for r in rows) for rows in runs.values()))
    out = {"notes": sorted(common), "systems": {}}
    print(f"{len(common)} notes scored for every system")
    for name, rows in runs.items():
        totals, per_row = score_rows(m.metrics, refs, [r for r in rows if r["row_index"] in common])
        out["systems"][name] = {
            "totals": {f"{t}/{v}": dict(c, WER=round(100 * (c["S"] + c["D"] + c["I"]) / c["N"], 2))
                       for (t, v), c in totals.items()},
            "per_row": [dict(row_index=i, track=t, view=v, **{k: c[k] for k in "SDIN"})
                        for (i, t, v), c in sorted(per_row.items())]}
        for key, c in out["systems"][name]["totals"].items():
            print(f"{name:12s} {key:40s} WER {c['WER']:6.2f}%  S {c['S']} D {c['D']} I {c['I']} N {c['N']}")
    (args.out / "scores.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--audio", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--profile", default="baseline")
    run.add_argument("--model")
    run.add_argument("--engine", default="whisper")
    run.set_defaults(func=cmd_run)
    score = sub.add_parser("score")
    score.add_argument("--references", required=True, type=Path)
    score.add_argument("--metrics", required=True, type=Path)
    score.add_argument("--out", required=True, type=Path)
    score.set_defaults(func=cmd_score)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

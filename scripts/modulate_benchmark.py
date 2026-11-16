"""
Benchmark on Modulate's Synthetic Medical Dictation (CC BY 4.0).

300 generated clinical notes read by text-to-speech voices in six recording
conditions (clean, telephone, low-bitrate MP3, fast, busy ward, all of them),
about 60% with dictated punctuation. Scored by term recall: the share of the
note's drugs, doses, diagnoses, findings (negated ones with their negation),
labs and values, names, chart numbers and so on that appear in the transcript,
in any of the accepted written forms. Splits are by note: tune on dev, check
on test.  https://huggingface.co/datasets/modulate/synthetic-medical-dictation

    modulate_benchmark.py export --parquet <file.parquet> --out <dir> [--notes 30]     (needs pyarrow)
    modulate_benchmark.py run    --out <dir> --profile candidate_full [--engine whisper] [--model <folder>]
    modulate_benchmark.py score  --out <dir>

Synthetic voices and generated text: read results as comparisons between
builds or systems, not as accuracy on real clinicians.
"""

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))


def norm(text: str) -> str:
    """The dataset's matching rule: lower case, punctuation dropped except inside numbers, letter-hyphens as spaces."""
    text = text.lower().replace("’", "'")
    text = re.sub(r"(?<=[^\W\d_])-(?=[^\W\d_])", " ", text)
    text = re.sub(r"(?<=\d)[.,/:](?=\d)", "\x00", text)              # keep 124.7, 1/2, 10:30
    text = re.sub(r"[^\w\x00 ]+", " ", text)
    return " " + " ".join(text.replace("\x00", ".").split()) + " "


def term_found(accept, transcript_norm: str) -> bool:
    return any(norm(form) in transcript_norm for form in accept)


def cmd_export(args):
    import pyarrow.parquet as pq
    args.out.mkdir(parents=True, exist_ok=True)
    rows, notes = [], []
    for batch in pq.ParquetFile(args.parquet).iter_batches(batch_size=16):
        for r in batch.to_pylist():
            note = r["id"].rsplit("-", 1)[0]
            if note not in notes:
                if args.notes and len(notes) >= args.notes:
                    continue
                notes.append(note)
            name = f"{r['id']}.{r['audio_format']}"
            (args.out / name).write_bytes(r["audio"]["bytes"])
            rows.append({"id": r["id"], "note": note, "file": name, "condition": r["condition"],
                         "specialty": r["specialty"], "dictated_punctuation": r["dictated_punctuation"],
                         "script": r["script"], "terms": r["terms"]})
    (args.out / "refs.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} recordings of {len(notes)} notes exported to {args.out}")


def cmd_run(args):
    import dictation_reliability as dr
    from faster_whisper import decode_audio

    profile = dr.PROFILES[args.profile]
    engine = dr.make_engine(args.engine, args.model, profile)
    style = dr.style_for(profile)
    builder, post = dr.build_text_pipeline(style, count=getattr(engine, "count_tokens", None), env={})
    rows = json.loads((args.out / "refs.json").read_text(encoding="utf-8"))
    tag = args.profile if args.engine == "whisper" else f"{args.engine}_{args.profile}"
    saved = args.out / f"out_{tag}.json"
    done = json.loads(saved.read_text(encoding="utf-8")) if saved.is_file() else {}
    t0, audio_s = time.perf_counter(), 0.0
    for n, r in enumerate(rows, 1):
        if r["id"] in done:
            continue
        audio = decode_audio(str(args.out / r["file"]), sampling_rate=16000)
        audio_s += len(audio) / 16000
        done[r["id"]] = dr.run_pipeline(engine, audio, None, style, builder, post, profile)[0]
        if n % 20 == 0:
            saved.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {tag} {n}/{len(rows)}", flush=True)
    saved.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{tag}: {len(done)} recordings, {audio_s / 60:.0f} min of new audio in {time.perf_counter() - t0:.0f} s")


def score(rows, texts):
    """{group: [found, total]} for conditions, term kinds and 'all'."""
    out = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        transcript = norm(texts.get(r["id"], ""))
        for term in r["terms"]:
            hit = term_found(term["accept"], transcript)
            for key in ("all", "condition:" + r["condition"], "kind:" + term["kind"]):
                out[key][0] += hit
                out[key][1] += 1
    return out


def cmd_score(args):
    rows = json.loads((args.out / "refs.json").read_text(encoding="utf-8"))
    systems = {p.stem[4:]: json.loads(p.read_text(encoding="utf-8")) for p in sorted(args.out.glob("out_*.json"))}
    common = set.intersection(*(set(t) for t in systems.values())) if systems else set()
    rows = [r for r in rows if r["id"] in common]
    scores = {name: score(rows, texts) for name, texts in systems.items()}
    keys = ["all"] + sorted(k for k in next(iter(scores.values())) if k != "all")
    print(f"{len(rows)} recordings scored for every system; term recall %")
    print(f"{'':28s}" + "".join(f"{name[:18]:>20s}" for name in scores))
    for key in keys:
        cells = "".join(f"{100 * s[key][0] / max(1, s[key][1]):13.1f} ({s[key][1]:4d})" for s in scores.values())
        print(f"{key:28s}{cells}")
    (args.out / "scores.json").write_text(json.dumps({n: dict(s) for n, s in scores.items()}, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--parquet", required=True, type=Path)
    e.add_argument("--out", required=True, type=Path)
    e.add_argument("--notes", type=int, default=0, help="only the first N notes (all their conditions)")
    e.set_defaults(func=cmd_export)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--profile", default="candidate_full")
    r.add_argument("--engine", default="whisper")
    r.add_argument("--model")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("score")
    s.add_argument("--out", required=True, type=Path)
    s.set_defaults(func=cmd_score)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

"""
eval_dictation.py — score transcription accuracy on a dictation test set.

Runs every file in a manifest (from make_test_dictation.py, or your own
recordings, see below) through the SAME pipeline the app uses
(ChunkedTranscriber: 30 s chunks cut at pauses, prompts, correction) under
several settings, and reports per setting and per microphone profile:

  WER          word error rate (lower is better)
  term recall  % of target medical terms transcribed correctly (higher is better)
  RTF          compute seconds per audio second

Settings (--variants):
  none        no prompt at all
  static      style example + recent text (the original 1060-edition behaviour)
  topics      style + topic-aware vocabulary + recent text
  topics+fix  topics, plus spelling correction (the app default)

  python scripts/eval_dictation.py --manifest testdict/manifest.json
  python scripts/eval_dictation.py --manifest testdict/manifest.json --variants static,topics+fix --show-missed

Your own recordings: put 16 kHz mono WAVs next to a manifest.json like
  [{"audio": "letter1.wav", "reference": "full text you read", "terms": ["apixaban", "HbA1c"],
    "profile": "tenor", "scenario": "letter1"}]
(the read_aloud/ scripts from make_test_dictation.py are written for this).
Test material must be fictional: transcripts may be printed with --show-missed.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bench_engine import load_wav                                       # noqa: E402
from chunked_transcriber import ChunkedTranscriber                      # noqa: E402
from eval_metrics import term_hits, word_error_rate                     # noqa: E402
from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs       # noqa: E402
from hw_profile import choose_config, detect_hardware                   # noqa: E402
from prompt_loader import load_prompt                                   # noqa: E402
from vocab import build_text_pipeline                                   # noqa: E402

VARIANTS = ("none", "static", "topics", "topics+fix")


class FiniteStream:
    """Serves a whole file as fast as the transcriber reads it, then b''."""

    def __init__(self, pcm16: np.ndarray):
        self.data, self.pos = pcm16.astype(np.int16).tobytes(), 0

    def read(self, n, exception_on_overflow=False):
        chunk = self.data[self.pos:self.pos + 2 * n]
        self.pos += len(chunk)
        return chunk

    def stop_stream(self):
        pass

    def close(self):
        pass


def make_variant(name, style, engine, base_builder, base_corrector):
    """(base_prompt, prompt_builder, postprocess) for a variant name."""
    if name == "none":
        return "", (lambda ctx: ""), None
    if name == "static":
        return style, None, None
    if name == "topics":
        return style, base_builder, None
    if name == "topics+fix":
        return style, base_builder, base_corrector
    raise SystemExit(f"unknown variant {name}")


def transcribe_file(engine, audio_f32, base_prompt, builder, post, chunk_s=None):
    pcm = (np.clip(audio_f32, -1, 1) * 32767).astype(np.int16)
    extra = {} if chunk_s is None else {"chunk_target_s": chunk_s}
    t = ChunkedTranscriber(engine, base_prompt, stream_factory=lambda: (FiniteStream(pcm), None),
                           prompt_builder=builder, postprocess=post, **extra)
    t0 = time.perf_counter()
    t.start_recording()
    t._capture_thread.join()
    t.stop_recording()
    t.wait_until_idle()
    return t.text, time.perf_counter() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score dictation accuracy across prompt/correction settings.")
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--profiles", help="only these mic profiles (comma list)")
    ap.add_argument("--model")
    ap.add_argument("--device", choices=["cuda", "cpu"])
    ap.add_argument("--compute-type")
    ap.add_argument("--beam-size", type=int)
    ap.add_argument("--chunk-s", type=float, help="chunk target in seconds (default: the app's)")
    ap.add_argument("--style-file", type=Path, help="style example to use instead of the app's")
    ap.add_argument("--max-new-tokens", type=int, help="random-weight test models only")
    ap.add_argument("--show-missed", action="store_true", help="list missed terms (fictional data only)")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.profiles:
        keep = set(args.profiles.split(","))
        entries = [e for e in entries if e.get("profile") in keep]
    base_dir = args.manifest.parent

    register_cuda_dll_dirs()
    cfg = choose_config(detect_hardware())
    if args.model:
        cfg.model = args.model
    if args.device:
        cfg.device = args.device
        if args.device == "cpu" and not args.compute_type:
            cfg.compute_type = "int8"
    if args.compute_type:
        cfg.compute_type = args.compute_type
    engine = FasterWhisperEngine(cfg, beam_size=args.beam_size)
    engine.warmup()
    if args.max_new_tokens:
        raw = engine.model.transcribe

        def capped(audio, **kw):
            kw.update(max_new_tokens=args.max_new_tokens, temperature=0.0)
            return raw(audio, **kw)
        engine.model.transcribe = capped

    style = args.style_file.read_text(encoding="utf-8").strip() if args.style_file else load_prompt()
    builder, corrector = build_text_pipeline(style, count=engine.count_tokens, env={})
    print(f"Model {cfg.model} on {cfg.device}/{cfg.compute_type}; {len(entries)} files; "
          f"corrector {'available' if corrector else 'MISSING (pip install rapidfuzz jellyfish wordfreq)'}")

    results = defaultdict(lambda: defaultdict(lambda: {"err": 0.0, "words": 0, "hit": 0, "terms": 0,
                                                       "audio": 0.0, "compute": 0.0}))
    missed = defaultdict(list)
    for variant in [v.strip() for v in args.variants.split(",") if v.strip()]:
        if variant == "topics+fix" and corrector is None:
            print("  skipping topics+fix (corrector unavailable)")
            continue
        base_prompt, vb, post = make_variant(variant, style, engine, builder, corrector)
        for e in entries:
            if vb is builder and builder is not None:
                builder._rotation.clear()              # each file starts fresh, like a new letter
            audio = load_wav(base_dir / e["audio"])
            hyp, secs = transcribe_file(engine, audio, base_prompt, vb, post, chunk_s=args.chunk_s)
            w, n = word_error_rate(e["reference"], hyp)
            found, miss = term_hits(e.get("terms", []), hyp)
            for key in (e.get("profile", "all"), "ALL"):
                r = results[variant][key]
                r["err"] += w * n
                r["words"] += n
                r["hit"] += len(found)
                r["terms"] += len(found) + len(miss)
                r["audio"] += len(audio) / 16000
                r["compute"] += secs
            missed[variant] += [(e.get("scenario"), e.get("profile"), m) for m in miss]
            print(f"  {variant:11s} {e['audio']:38s} WER {w * 100:5.1f}%  terms {len(found)}/{len(found) + len(miss)}")

    profiles = sorted({k for v in results.values() for k in v if k != "ALL"}) + ["ALL"]
    print("\nWER % (lower is better) / term recall % (higher is better)")
    print(f"{'variant':12s}" + "".join(f"{p:>18s}" for p in profiles) + f"{'RTF':>8s}")
    summary = {}
    for variant, by in results.items():
        row = f"{variant:12s}"
        summary[variant] = {}
        for p in profiles:
            r = by.get(p)
            if not r or not r["words"]:
                row += f"{'-':>18s}"
                continue
            wer = 100 * r["err"] / r["words"]
            rec = 100 * r["hit"] / max(1, r["terms"])
            summary[variant][p] = {"wer": round(wer, 1), "term_recall": round(rec, 1)}
            row += f"{wer:9.1f} /{rec:6.1f}  "
        rtf = by["ALL"]["compute"] / max(1e-9, by["ALL"]["audio"])
        summary[variant]["rtf"] = round(rtf, 3)
        print(row + f"{rtf:8.3f}")
    if corrector is not None:
        print(f"\nSpelling corrections applied in total: {corrector.total_corrections}")
    if args.show_missed:
        for variant, items in missed.items():
            print(f"\nMissed terms [{variant}]:")
            for scen, prof, term in items:
                print(f"  {scen} / {prof}: {term}")
    if args.json:
        args.json.write_text(json.dumps({"model": cfg.model, "device": cfg.device,
                                         "compute_type": cfg.compute_type, "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

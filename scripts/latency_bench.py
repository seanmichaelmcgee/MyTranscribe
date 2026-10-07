"""
latency_bench.py — how long after Stop does the text appear, by dictation length and model?

Drives the real ChunkedTranscriber (same chunking, prompts and correction as the
app) with synthetic dictation audio fed faster than real time, presses Stop after
D seconds of audio, and times Stop -> final text. Feeding at 2x real time doesn't
change the result as long as the worker keeps up during dictation (it reports
max queue depth so you can check). Synthetic, fictional audio only.

    venv1060\\Scripts\\python.exe scripts\\latency_bench.py --models large-v3-turbo,large-v3 ^
        --json results_1060\\latency.json
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from chunked_transcriber import ChunkedTranscriber, SAMPLE_RATE as SR   # noqa: E402
from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs         # noqa: E402
from hw_profile import EngineConfig                                       # noqa: E402
from prompt_loader import load_prompt                                     # noqa: E402
from stress_pipeline import LoopStream, load_wav                          # noqa: E402
from vocab import build_text_pipeline                                     # noqa: E402


def session(engine, audio, prompt, pipeline, seconds, chunk_s, speed):
    """Record `seconds` of audio, press Stop, return (latency_s, max_queue, chunks)."""
    stream = LoopStream(audio, speed=speed)
    t = ChunkedTranscriber(engine, prompt, stream_factory=lambda: (stream, None), chunk_target_s=chunk_s,
                           prompt_builder=pipeline[0], postprocess=pipeline[1])
    t.start_recording()
    max_q = 0
    while stream.served < seconds * SR * 2:
        max_q = max(max_q, t.queue_depth)
        time.sleep(0.01)
    t0 = time.perf_counter()
    t.stop_recording()
    t.wait_until_idle()
    return time.perf_counter() - t0, max_q, len(t.chunk_stats)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--models", default="large-v3-turbo,large-v3")
    ap.add_argument("--compute-type", default="int8_float32")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--durations", default="5,10,20,30,45,60")
    ap.add_argument("--chunks", default="30,15", help="chunk targets to try (15 only for >= 20 s)")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--speed", type=float, default=2.0)
    ap.add_argument("--profile", default="conference")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)

    register_cuda_dll_dirs()
    td = ROOT / "results_1060" / "testdict"
    audio = np.concatenate([load_wav(p) for p in sorted(td.glob(f"*__{args.profile}.wav"))])
    durations = [float(d) for d in args.durations.split(",")]
    chunks = [float(c) for c in args.chunks.split(",")]
    base_prompt = load_prompt()
    rng = random.Random(7)
    results = []
    for model in args.models.split(","):
        cfg = EngineConfig(model, "cuda", args.compute_type, 2, "latency bench")
        t_load = time.perf_counter()
        eng = FasterWhisperEngine(cfg, beam_size=args.beam_size)
        eng.warmup()
        load_s = time.perf_counter() - t_load
        pipeline = build_text_pipeline(base_prompt, count=getattr(eng, "count_tokens", None))
        print(f"\n== {model} {args.compute_type} beam {args.beam_size} (load+warmup {load_s:.1f}s) ==")
        print(f"{'dictation':>9} {'chunk':>5} {'latency mean':>13} {'max':>6} {'queue':>5}")
        for chunk_s in chunks:
            for d in durations:
                if chunk_s < max(chunks) and d < 20:
                    continue
                lats, qs = [], []
                for _ in range(args.trials):
                    off = rng.randrange(0, len(audio) - 1)
                    lat, q, n = session(eng, np.roll(audio, -off), base_prompt, pipeline, d, chunk_s, args.speed)
                    lats.append(lat)
                    qs.append(q)
                row = dict(model=model, compute=args.compute_type, beam=args.beam_size, dictation_s=d, chunk_s=chunk_s,
                           latency_mean=round(float(np.mean(lats)), 2), latency_max=round(max(lats), 2),
                           max_queue=max(qs), load_s=round(load_s, 1))
                results.append(row)
                print(f"{d:>8.0f}s {chunk_s:>4.0f}s {row['latency_mean']:>12.2f}s {row['latency_max']:>5.2f}s "
                      f"{row['max_queue']:>5}")
        del eng
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

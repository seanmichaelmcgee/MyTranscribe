"""
bench_engine.py — measure faster-whisper speed and memory on THIS machine.

Run it on the GTX 1060 box before trusting the app with long letters:

    python scripts/bench_engine.py --audio my_dictation.wav
    python scripts/bench_engine.py --audio my_dictation.wav --reference my_dictation.txt
    python scripts/bench_engine.py --audio a.wav --model large-v3 --compute-type int8_float32

Reports: chosen config, load time, per-30 s-chunk time and real-time factor
(RTF = compute seconds / audio seconds; must stay well under 1.0), peak
process RAM, peak GPU memory (nvidia-smi sampling), and word error rate if a
reference transcript is given.

--encoder-only / --max-new-tokens exist for random-weight test models (see
make_random_whisper.py), whose decoder never stops on its own.

Audio: any 16 kHz mono 16-bit WAV. Convert others with
    ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 out.wav
Your recordings contain PHI: keep them on the clinical machine; the script
prints only timing, sizes and WER, never the transcript (unless --show-text).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs  # noqa: E402
from hw_profile import EngineConfig, choose_config, detect_hardware  # noqa: E402
from prompt_loader import load_prompt  # noqa: E402

SR = 16000


def load_wav(path):
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{path}: need 16 kHz mono 16-bit WAV (see --help for ffmpeg command)")
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


def wer(ref, hyp):
    """Word error rate (lower-cased, punctuation stripped). Plain Levenshtein on words."""
    norm = lambda s: re.sub(r"[^a-z0-9' ]+", " ", s.lower()).split()
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / max(1, len(r))


class PeakSampler:
    """Samples process RSS (psutil) and GPU memory (nvidia-smi) every 0.5 s."""

    def __init__(self):
        self.rss_mb = 0.0
        self.gpu_mb = None
        self._stop = threading.Event()
        self._smi = shutil.which("nvidia-smi")
        try:
            import psutil
            self._proc = psutil.Process()
        except ImportError:
            self._proc = None
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            if self._proc is not None:
                self.rss_mb = max(self.rss_mb, self._proc.memory_info().rss / 2**20)
            if self._smi:
                try:
                    out = subprocess.run([self._smi, "--query-gpu=memory.used",
                                          "--format=csv,noheader,nounits"],
                                         capture_output=True, text=True, timeout=5).stdout
                    used = float(out.strip().splitlines()[0])
                    self.gpu_mb = used if self.gpu_mb is None else max(self.gpu_mb, used)
                except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                    pass
            self._stop.wait(0.5)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Benchmark faster-whisper on this machine.")
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--reference", type=Path, help="text file with the true transcript (for WER)")
    ap.add_argument("--model", help="override model name/path")
    ap.add_argument("--device", choices=["cuda", "cpu"])
    ap.add_argument("--compute-type")
    ap.add_argument("--beam-size", type=int)
    ap.add_argument("--chunk-s", type=float, default=30.0, help="chunk length, like the app")
    ap.add_argument("--repeat", type=int, default=1, help="run the whole file N times")
    ap.add_argument("--no-prompt", action="store_true", help="skip the medical vocabulary prompt")
    ap.add_argument("--encoder-only", action="store_true",
                    help="random-weight models: decode 1 token per chunk (measures encoder cost)")
    ap.add_argument("--max-new-tokens", type=int,
                    help="random-weight models: cap decoded tokens per window")
    ap.add_argument("--json", type=Path, help="also write results to this JSON file")
    ap.add_argument("--show-text", action="store_true", help="print the transcript (PHI!)")
    args = ap.parse_args(argv)

    register_cuda_dll_dirs()
    hw = detect_hardware()
    cfg = choose_config(hw)
    if args.model:
        cfg.model = args.model
    if args.device:
        cfg.device = args.device
        if args.device == "cpu" and not args.compute_type:
            cfg.compute_type = "int8"
    if args.compute_type:
        cfg.compute_type = args.compute_type

    audio = load_wav(args.audio)
    prompt = "" if args.no_prompt else load_prompt()
    print(f"Hardware: {hw}")
    print(f"Config:   model={cfg.model} device={cfg.device} compute={cfg.compute_type} "
          f"threads={cfg.cpu_threads}  ({cfg.reason})")
    print(f"Audio:    {len(audio) / SR:.1f} s x {args.repeat}")

    results = {"config": cfg.__dict__, "hardware": {k: (sorted(v) if isinstance(v, frozenset) else v)
                                                   for k, v in hw.__dict__.items()}}
    with PeakSampler() as peaks:
        eng = FasterWhisperEngine(cfg, beam_size=args.beam_size)
        results["load_s"] = eng.load_seconds
        t0 = time.perf_counter()
        eng.warmup()
        results["warmup_s"] = time.perf_counter() - t0

        if args.encoder_only or args.max_new_tokens:
            cap = 1 if args.encoder_only else args.max_new_tokens
            raw = eng.model.transcribe

            def capped(audio_, **kw):
                kw.update(max_new_tokens=cap, temperature=0.0)
                return raw(audio_, **kw)
            eng.model.transcribe = capped

        step = int(args.chunk_s * SR)
        chunk_times, texts = [], []
        for _ in range(args.repeat):
            for i in range(0, len(audio), step):
                piece = audio[i:i + step]
                t = time.perf_counter()
                texts.append(eng.transcribe(piece, prompt))
                chunk_times.append((len(piece) / SR, time.perf_counter() - t))

    audio_total = sum(a for a, _ in chunk_times)
    compute_total = sum(c for _, c in chunk_times)
    rtfs = [c / a for a, c in chunk_times if a > 1]
    results.update(
        chunks=len(chunk_times), audio_s=audio_total, compute_s=compute_total,
        rtf_mean=compute_total / audio_total, rtf_max=max(rtfs) if rtfs else None,
        stop_latency_estimate_s=max(c for _, c in chunk_times),
        peak_rss_mb=round(peaks.rss_mb), peak_gpu_mb=peaks.gpu_mb,
    )
    hyp = " ".join(t for t in texts if t)
    if args.reference:
        ref = args.reference.read_text(encoding="utf-8")
        results["wer"] = wer(ref * args.repeat if args.repeat > 1 else ref, hyp)

    print(f"Load {results['load_s']:.1f}s, warmup {results['warmup_s']:.1f}s")
    print(f"{results['chunks']} chunks: RTF mean {results['rtf_mean']:.3f}, "
          f"max {results['rtf_max'] or 0:.3f} -> a {args.chunk_s:.0f}s chunk takes "
          f"~{results['rtf_mean'] * args.chunk_s:.1f}s")
    print(f"Peak RAM {results['peak_rss_mb']} MB, peak GPU {results['peak_gpu_mb'] or 'n/a'} MB "
          f"(GPU figure is whole-card usage incl. desktop)")
    if "wer" in results:
        print(f"WER {results['wer'] * 100:.1f}%")
    if args.show_text:
        print("\n" + hyp)
    if args.json:
        args.json.write_text(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

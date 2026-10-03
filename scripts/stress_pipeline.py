"""
stress_pipeline.py — stress the full ChunkedTranscriber + faster-whisper stack.

Feeds synthetic or recorded dictation through the real recording/chunking/
worker threads and the real faster-whisper engine (no microphone needed), and
checks for: lost/duplicated audio, backlog growth, memory growth, thread
leaks, stop latency, error handling, and GUI event-loop stalls.

Examples
  # everything, with a real model (on the 1060 box):
  python scripts/stress_pipeline.py --audio dictation.wav --all
  # random-weight model in a sandbox (decoder capped to a realistic length):
  python scripts/stress_pipeline.py --audio letter.wav --model /tmp/rand-turbo \
      --max-new-tokens 120 --scenario long --minutes 10

Scenarios
  long     one session of --minutes of dictation at --speed x real time
  cycles   --cycles short sessions (0.2-3 s), like quick hotkey taps
  silence  5 min of silence + 5 min of room noise: engine must not be called
  faults   microphone dies mid-session; engine raises on one chunk
  gui      Qt window driven through hotkey start/stop; measures UI stalls
           (needs a display; use xvfb-run on Linux)

Exit code is non-zero if any check fails. Results also go to --json.
Transcript text is never printed.
"""

import argparse
import gc
import json
import logging
import os
import random
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chunked_transcriber import ChunkedTranscriber, SAMPLE_RATE as SR  # noqa: E402
from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs        # noqa: E402
from hw_profile import choose_config, detect_hardware                    # noqa: E402
from prompt_loader import load_prompt                                    # noqa: E402
from vocab import build_text_pipeline                                    # noqa: E402

# (prompt_builder, corrector) shared by all scenarios; set in main().
PIPELINE = (None, None)

log = logging.getLogger("stress")


# ── Audio sources ────────────────────────────────────────────────────────────
class LoopStream:
    """PyAudio-like stream looping int16 audio, paced at `speed` x real time (0 = no pacing)."""

    def __init__(self, samples, speed=1.0, total_s=None, fail_after_s=None):
        self.data = samples.astype(np.int16).tobytes()
        self.pos = 0
        self.speed = speed
        self.total_bytes = None if total_s is None else int(total_s * SR) * 2
        self.fail_after_bytes = None if fail_after_s is None else int(fail_after_s * SR) * 2
        self.served = 0
        self.t0 = time.perf_counter()

    def read(self, n, exception_on_overflow=False):
        if self.fail_after_bytes is not None and self.served >= self.fail_after_bytes:
            raise OSError(-9988, "Stream closed (simulated USB unplug)")
        need = n * 2
        if self.total_bytes is not None:
            need = min(need, self.total_bytes - self.served)
            if need <= 0:
                return b""
        if self.speed:
            # Sleep until wall-clock catches up with the audio we've served.
            due = self.t0 + (self.served + need) / 2 / SR / self.speed
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        out = bytearray()
        while len(out) < need:
            take = self.data[self.pos:self.pos + need - len(out)]
            out += take
            self.pos = (self.pos + len(take)) % len(self.data)
        self.served += len(out)
        return bytes(out)

    def stop_stream(self):
        pass

    def close(self):
        pass


def load_wav(path):
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2, \
            "need 16 kHz mono 16-bit WAV"
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def rss_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except ImportError:
        return float("nan")


# ── Engine ───────────────────────────────────────────────────────────────────
def build_engine(args):
    register_cuda_dll_dirs()
    cfg = choose_config(detect_hardware())
    if args.model:
        cfg.model = args.model
    if args.device:
        cfg.device = args.device
        if args.device == "cpu":
            cfg.compute_type = args.compute_type or "int8"
    if args.compute_type:
        cfg.compute_type = args.compute_type
    eng = FasterWhisperEngine(cfg, beam_size=args.beam_size)
    eng.warmup()
    if args.max_new_tokens:
        raw = eng.model.transcribe

        def capped(audio, **kw):
            kw.update(max_new_tokens=args.max_new_tokens, temperature=0.0)
            return raw(audio, **kw)
        eng.model.transcribe = capped
    log.info("Engine: %s %s %s", cfg.model, cfg.device, cfg.compute_type)
    return eng


class CountingEngine:
    """Wraps an engine: counts calls/samples, optionally raises on given call indexes."""

    def __init__(self, inner, fail_on=()):
        self.inner, self.fail_on = inner, set(fail_on)
        self.calls = 0
        self.samples = 0
        self.lock = threading.Lock()

    def transcribe(self, audio, prompt=None):
        with self.lock:
            i = self.calls
            self.calls += 1
            self.samples += len(audio)
        if i in self.fail_on:
            raise RuntimeError("CUDA failed with error out of memory (injected)")
        return self.inner.transcribe(audio, prompt)


# ── Checks ───────────────────────────────────────────────────────────────────
class Report:
    def __init__(self):
        self.results = {}
        self.failures = []

    def check(self, scenario, name, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} {detail}")
        self.results.setdefault(scenario, {}).setdefault("checks", {})[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            self.failures.append(f"{scenario}:{name}")

    def metric(self, scenario, **kw):
        self.results.setdefault(scenario, {}).setdefault("metrics", {}).update(kw)


def run_session(engine, stream, prompt, max_session_s=3600, stop_after_s=None):
    """One recording session; returns (transcriber, stop_latency_s, max_queue, rss_samples)."""
    t = ChunkedTranscriber(engine, prompt, stream_factory=lambda: (stream, None),
                           max_session_s=max_session_s,
                           prompt_builder=PIPELINE[0], postprocess=PIPELINE[1])
    t.start_recording()
    start = time.perf_counter()
    max_q, rss = 0, []
    next_rss = start
    while t.recording:
        max_q = max(max_q, t.queue_depth)
        if time.perf_counter() >= next_rss:
            rss.append(round(rss_mb()))
            next_rss += 10
        if stop_after_s is not None and time.perf_counter() - start >= stop_after_s:
            break
        time.sleep(0.05)
    t0 = time.perf_counter()
    t.stop_recording()
    stop_call = time.perf_counter() - t0
    t.wait_until_idle()
    latency = time.perf_counter() - t0
    rss.append(round(rss_mb()))
    return t, stop_call, latency, max_q, rss


def scenario_long(args, engine, audio, prompt, rep):
    name = "long"
    minutes = args.minutes
    print(f"\n== long: {minutes} min dictation at {args.speed}x real time ==")
    eng = CountingEngine(engine)
    stream = LoopStream(audio, speed=args.speed, total_s=minutes * 60)
    threads0 = threading.active_count()
    t, stop_call, latency, max_q, rss = run_session(eng, stream, prompt)
    expected = int(minutes * 60 * SR)
    silent_skipped = expected - eng.samples
    stats = t.chunk_stats
    rtfs = [s.rtf for s in stats if s.audio_s > 5]
    rep.metric(name, audio_min=minutes, chunks=len(stats), engine_calls=eng.calls,
               rtf_mean=round(float(np.mean(rtfs)), 3) if rtfs else None,
               rtf_max=round(max(rtfs), 3) if rtfs else None,
               max_queue=max_q, stop_call_s=round(stop_call, 3),
               final_latency_s=round(latency, 2), rss_mb_series=rss,
               text_chars=len(t.text))
    rep.check(name, "all audio reached engine or was silent-skipped",
              eng.samples <= expected and silent_skipped < 30 * SR,
              f"(engine got {eng.samples / SR:.1f}s of {expected / SR:.1f}s)")
    rep.check(name, "stop_recording() returns fast", stop_call < 0.5, f"({stop_call:.3f}s)")
    if args.speed and args.speed <= 1.0:
        rep.check(name, "keeps up with live dictation (queue <= 2)", max_q <= 2, f"(max queue {max_q})")
        rep.check(name, "final text within 1.5 chunk-times of stop",
                  latency <= 1.5 * max((s.elapsed_s for s in stats), default=1) + 1,
                  f"({latency:.1f}s)")
    growth = (rss[-1] - rss[1]) if len(rss) > 2 else 0
    rep.check(name, "memory stable (< 300 MB growth after first sample)", growth < 300,
              f"(RSS {rss[0]} -> {rss[-1]} MB)")
    rep.check(name, "no leaked threads", wait_threads(threads0), "")
    rep.check(name, "no transcription errors",
              not any(x.startswith("[Transcription Error") for x in t.transcriptions))


def wait_threads(baseline, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if threading.active_count() <= baseline:
            return True
        time.sleep(0.05)
    return threading.active_count() <= baseline


def scenario_cycles(args, engine, audio, prompt, rep):
    name = "cycles"
    print(f"\n== cycles: {args.cycles} short sessions ==")
    rng = random.Random(1)
    eng = CountingEngine(engine)
    threads0 = threading.active_count()
    gc.collect()
    rss0 = rss_mb()
    latencies, errors = [], 0
    rss_mid = None
    for i in range(args.cycles):
        dur = rng.uniform(0.2, 3.0)
        offset = rng.randrange(0, max(1, len(audio) - int(3 * SR)))
        stream = LoopStream(audio[offset:], speed=args.cycle_speed, total_s=dur)
        try:
            t, _, latency, _, _ = run_session(eng, stream, prompt)
            latencies.append(latency)
        except Exception:
            log.exception("cycle %d failed", i)
            errors += 1
        if i == args.cycles // 5:
            gc.collect()
            rss_mid = rss_mb()
    gc.collect()
    rss1 = rss_mb()
    rep.metric(name, cycles=args.cycles, engine_calls=eng.calls,
               latency_p50=round(float(np.median(latencies)), 2),
               latency_max=round(max(latencies), 2),
               rss_mb=[round(rss0), round(rss_mid or rss0), round(rss1)])
    rep.check(name, "no exceptions", errors == 0, f"({errors})")
    rep.check(name, "no leaked threads", wait_threads(threads0),
              f"({threading.active_count()} vs {threads0})")
    rep.check(name, "memory flat after warm-up (< 100 MB)",
              rss1 - (rss_mid or rss0) < 100, f"({rss_mid:.0f} -> {rss1:.0f} MB)")


def scenario_silence(args, engine, audio, prompt, rep):
    name = "silence"
    print("\n== silence: 5 min digital silence, 5 min quiet room noise ==")
    rng = np.random.default_rng(0)
    for label, samples in (("digital silence", np.zeros(SR, np.int16)),
                           ("room noise rms~40", (rng.standard_normal(SR * 5) * 40).astype(np.int16))):
        eng = CountingEngine(engine)
        t, *_ = run_session(eng, LoopStream(samples, speed=0, total_s=300), prompt)
        rep.check(name, f"{label}: engine never called, empty text",
                  eng.calls == 0 and t.text == "", f"(calls={eng.calls})")
    # Clipping: max-volume speech must not crash anything.
    loud = np.clip(audio.astype(np.int32) * 20, -32768, 32767).astype(np.int16)
    eng = CountingEngine(engine)
    t, *_ = run_session(eng, LoopStream(loud, speed=0, total_s=60), prompt)
    rep.check(name, "clipped/over-loud audio handled", eng.calls >= 2 and
              not any(x.startswith("[Transcription Error") for x in t.transcriptions))


def scenario_faults(args, engine, audio, prompt, rep):
    name = "faults"
    print("\n== faults: mic unplug mid-session, engine error on one chunk ==")
    eng = CountingEngine(engine)
    stream = LoopStream(audio, speed=0, total_s=600, fail_after_s=75)
    t0 = time.perf_counter()
    t, *_ = run_session(eng, stream, prompt)
    rep.check(name, "mic failure ends session with a message",
              t.auto_stopped and bool(t.capture_error), f"({t.capture_error})")
    rep.check(name, "audio before the failure is still transcribed",
              abs(eng.samples / SR - 75) < 31, f"({eng.samples / SR:.1f}s of 75s)")
    rep.metric(name, unplug_detect_and_finish_s=round(time.perf_counter() - t0, 2))

    eng = CountingEngine(engine, fail_on={1})
    t, *_ = run_session(eng, LoopStream(audio, speed=0, total_s=120), prompt)
    errs = [x for x in t.transcriptions if x.startswith("[Transcription Error")]
    rep.check(name, "engine error reported once, later chunks continue",
              len(errs) == 1 and eng.calls >= 4 and len(t.transcriptions) == eng.calls,
              f"(calls={eng.calls}, errors={len(errs)})")


def scenario_gui(args, engine, audio, prompt, rep):
    """Drive the real window; measure the longest gap between 10 ms timer ticks."""
    name = "gui"
    print(f"\n== gui: {args.gui_cycles} hotkey start/stop cycles with live engine ==")
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    import gui_qt
    import gui_med
    import phi_clipboard
    gui_qt.HotkeyBridge.start = lambda self: None
    gui_qt.HotkeyBridge.stop = lambda self: None
    pastes = []
    phi_clipboard.send_paste = lambda *a, **k: pastes.append(1)
    app = QApplication.instance() or QApplication([])

    streams = []

    def factory():
        off = random.randrange(0, len(audio) - 10 * SR)
        s = LoopStream(audio[off:], speed=1.0)
        streams.append(s)
        return s, None

    w = gui_med.MedTranscriptionWindow(engine_factory=lambda: engine, stream_factory=factory,
                                       autopaste=True, base_prompt=prompt, text_pipeline=PIPELINE)
    w._chime.play_start = w._chime.play_end = lambda: None
    w.show()

    gaps = []
    last = [time.perf_counter()]

    def tick():
        now = time.perf_counter()
        gaps.append(now - last[0])
        last[0] = now
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(tick)
    timer.start()

    def pump(seconds=None, until=None, limit=120):
        end = time.perf_counter() + (seconds if seconds is not None else limit)
        while time.perf_counter() < end:
            app.processEvents()
            if until is not None and until():
                return True
            time.sleep(0.002)
        return until is None

    pump(until=lambda: w.ready, limit=60)
    rng = random.Random(2)
    finished = 0
    for i in range(args.gui_cycles):
        w.on_hotkey()                        # start
        pump(seconds=rng.uniform(1.0, 8.0))
        w.on_hotkey()                        # stop
        if pump(until=lambda: not w._finishing, limit=120):
            finished += 1
        pump(seconds=0.3)
    timer.stop()
    worst = max(gaps) if gaps else 0
    p99 = float(np.percentile(gaps, 99)) if gaps else 0
    rep.metric(name, cycles=args.gui_cycles, finished=finished, pastes=len(pastes),
               max_ui_gap_ms=round(worst * 1000), p99_ui_gap_ms=round(p99 * 1000))
    rep.check(name, "every cycle finished", finished == args.gui_cycles, f"({finished})")
    rep.check(name, "auto-paste fired once per non-empty result",
              len(pastes) <= finished and len(pastes) >= finished - 2, f"({len(pastes)})")
    rep.check(name, "UI never froze > 250 ms", worst < 0.25, f"(worst {worst * 1000:.0f} ms, p99 {p99 * 1000:.0f} ms)")
    w.close()


SCENARIOS = {"long": scenario_long, "cycles": scenario_cycles, "silence": scenario_silence,
             "faults": scenario_faults, "gui": scenario_gui}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stress the MyTranscribe medical pipeline.")
    ap.add_argument("--audio", required=True, type=Path, help="16 kHz mono 16-bit WAV of dictation")
    ap.add_argument("--scenario", action="append", choices=sorted(SCENARIOS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--device", choices=["cuda", "cpu"])
    ap.add_argument("--compute-type")
    ap.add_argument("--beam-size", type=int)
    ap.add_argument("--max-new-tokens", type=int, help="cap decoder (random-weight models only)")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--speed", type=float, default=1.0, help="x real time for 'long' (0 = flat out)")
    ap.add_argument("--cycles", type=int, default=200)
    ap.add_argument("--cycle-speed", type=float, default=10.0)
    ap.add_argument("--gui-cycles", type=int, default=20)
    ap.add_argument("--no-prompt", action="store_true")
    ap.add_argument("--no-vocab", action="store_true", help="static prompt only, no topic terms/correction")
    ap.add_argument("--json", type=Path)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    chosen = sorted(SCENARIOS) if args.all else (args.scenario or ["long"])
    audio = load_wav(args.audio)
    prompt = "" if args.no_prompt else load_prompt()
    engine = build_engine(args)
    global PIPELINE
    if not args.no_vocab:
        PIPELINE = build_text_pipeline(prompt, count=engine.count_tokens, env={})
    rep = Report()
    rep.results["_meta"] = {"model": engine.config.model, "device": engine.config.device,
                            "compute_type": engine.config.compute_type,
                            "max_new_tokens": args.max_new_tokens, "cpu_count": os.cpu_count(),
                            "vocab": not args.no_vocab}
    t0 = time.perf_counter()
    for s in chosen:
        SCENARIOS[s](args, engine, audio, prompt, rep)
    rep.results["_meta"]["wall_s"] = round(time.perf_counter() - t0, 1)
    print("\nMetrics:")
    for k, v in rep.results.items():
        if k != "_meta":
            print(f"  {k}: {v.get('metrics')}")
    if args.json:
        args.json.write_text(json.dumps(rep.results, indent=2, default=str))
    print(f"\n{'ALL CHECKS PASSED' if not rep.failures else 'FAILED: ' + ', '.join(rep.failures)}")
    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())

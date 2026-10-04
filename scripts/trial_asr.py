"""Replay the SAME local fictional corpus through Whisper or isolated MedASR.

No microphone/clipboard/GUI access. Offline playback defaults to fast file replay;
--realtime paces frames and measures final Stop->text separately from compute.
Raw and app-cleaned transcripts go only to gitignored local JSON, never stdout.
"""
import argparse
import importlib.metadata
import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

from asr_trial_common import (MODEL_REVISION, ROOT, SR, load_corpus, local_result_path,
                              sha256, source_hashes, source_revision, write_json)
sys.path.insert(0, str(ROOT / "src"))


class ReplayStream:
    def __init__(self, pcm: bytes, realtime: bool = False):
        self.pcm, self.pos, self.realtime = pcm, 0, realtime
        self.started = time.perf_counter()
        self.finished = None

    def read(self, n, exception_on_overflow=False):
        data = self.pcm[self.pos:self.pos + n * 2]
        self.pos += len(data)
        if data and self.realtime:
            remaining = self.started + self.pos / (2 * SR) - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
        if not data:
            self.finished = time.perf_counter()
        return data

    def stop_stream(self):
        pass

    def close(self):
        pass


class CaptureEngine:
    def __init__(self, engine):
        self.engine, self.raw_chunks, self.chunk_times = engine, [], []

    def transcribe(self, audio, prompt=None):
        start = time.perf_counter()
        text = self.engine.transcribe(audio, prompt)
        sync = getattr(self.engine, "synchronize", None)
        if sync:
            sync()
        self.chunk_times.append(time.perf_counter() - start)
        self.raw_chunks.append(text)
        return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", required=True, choices=("whisper", "medasr"))
    ap.add_argument("--manifest", action="append", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only")
    ap.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    ap.add_argument("--precision", choices=("float32", "float16"), default="float32")
    ap.add_argument("--medasr-format", choices=("none", "native-v1"), default="none")
    ap.add_argument("--model-path", type=Path, default=ROOT / "models_medasr" / MODEL_REVISION)
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--repeats", type=int, default=1)
    args = ap.parse_args(argv)
    if args.repeats < 1 or args.repeats > 10:
        ap.error("--repeats must be 1..10")
    if args.engine != "medasr" and args.medasr_format != "none":
        ap.error("--medasr-format applies only to MedASR")
    out = local_result_path(args.out)
    entries, corpus_hash = load_corpus(args.manifest, args.only)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from chunked_transcriber import ChunkedTranscriber, filter_phantoms
    from prompt_loader import load_prompt
    from text_fixes import BUNDLED_CORRECTIONS
    from vocab import build_text_pipeline
    style = load_prompt(env={})
    # Freeze correction inputs to the committed rules, excluding per-user hidden state.
    load_start = time.perf_counter()
    if args.engine == "medasr":
        from medasr_engine import MedASREngine
        engine = MedASREngine(args.model_path, args.device, args.precision)
        config = dict(model="google/medasr", revision=MODEL_REVISION, precision=args.precision,
                      device=args.device, decoding="greedy CTC", gpu=engine.gpu_name,
                      format_mode=args.medasr_format)
        builder = None
        base_prompt = ""
        _, post = build_text_pipeline(style, env={}, correction_files=[BUNDLED_CORRECTIONS])
        if args.medasr_format == "native-v1":
            from medasr_native_format import postprocess_native
            shared_post = post
            post = lambda text: postprocess_native(text, shared_post)
    else:
        from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs
        from hw_profile import EngineConfig
        register_cuda_dll_dirs()
        engine = FasterWhisperEngine(EngineConfig("large-v3", args.device,
            "int8_float32" if args.device == "cuda" else "int8", 8, "Frozen comparison baseline"), beam_size=5)
        if engine.config.device != args.device:
            raise RuntimeError("Whisper fell back to CPU; refusing mislabeled GPU timings")
        builder, post = build_text_pipeline(style, count=engine.count_tokens, env={},
                                           correction_files=[BUNDLED_CORRECTIONS])
        base_prompt = style
        config = dict(model="large-v3", device=args.device,
                      compute="int8_float32" if args.device == "cuda" else "int8", beam=5, patience=2.0)
    load_s = time.perf_counter() - load_start
    # A real waveform warmup avoids silence shortcuts. No reference/terms fed to either model.
    with wave.open(str(entries[0]["_path"]), "rb") as w:
        warm_audio = np.frombuffer(w.readframes(min(w.getnframes(), SR * 10)), dtype="<i2").astype(np.float32) / 32768.0
    warm_start = time.perf_counter()
    engine.transcribe(warm_audio, base_prompt)
    if hasattr(engine, "synchronize"):
        engine.synchronize()
    warmup_s = time.perf_counter() - warm_start
    versions = {}
    for name in ("numpy", "transformers", "torch", "faster-whisper", "ctranslate2", "wordfreq", "rapidfuzz", "jellyfish"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    record = dict(schema=1, engine=args.engine, corpus_sha256=corpus_hash, source_revision=source_revision(),
                  config=config, versions=versions, chunk_target_s=20, replay="realtime" if args.realtime else "offline",
                  load_s=load_s, warmup_s=warmup_s, repeats=args.repeats,
                  correction_sha256=sha256(BUNDLED_CORRECTIONS), source_sha256=source_hashes(), utterances=[], completed=False)
    if args.engine == "medasr":
        record["model_integrity"] = engine.provenance
    write_json(out, record)
    for repeat in range(args.repeats):
        for i, entry in enumerate(entries):
            with wave.open(str(entry["_path"]), "rb") as w:
                pcm = w.readframes(w.getnframes())
            # Match the historical replay harness' int16->float->int16 conversion.
            pcm = (np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0 * 32767).astype("<i2").tobytes()
            stream = ReplayStream(pcm, args.realtime)
            capture = CaptureEngine(engine)
            if hasattr(engine, "reset_peak_memory"):
                engine.reset_peak_memory()
            transcriber = ChunkedTranscriber(capture, stream_factory=lambda: (stream, None),
                                            base_prompt=base_prompt, prompt_builder=builder,
                                            postprocess=post, chunk_target_s=20.0)
            start = time.perf_counter()
            transcriber.start_recording()
            transcriber._capture_thread.join(timeout=entry["duration_s"] + 30)
            if transcriber._capture_thread.is_alive():
                transcriber.stop_recording()
                raise RuntimeError("Replay capture timed out")
            stop_time = time.perf_counter()
            backlog_at_stop = transcriber._queue.qsize()
            transcriber.stop_recording()
            stop_call_s = time.perf_counter() - stop_time
            if not transcriber.wait_until_idle(timeout=180):
                raise RuntimeError("Transcription timed out")
            from voice_commands import apply
            cleaned = apply(transcriber.text)
            if "[Transcription Error:" in cleaned:
                raise RuntimeError("Engine failed; refusing to score a failed transcription")
            end = time.perf_counter()
            item = dict(clip_id=entry["clip_id"], audio=entry["audio"], audio_sha256=entry["audio_sha256"],
                        repeat=repeat, duration_s=entry["duration_s"], raw=" ".join(capture.raw_chunks),
                        filtered=" ".join(filter_phantoms(t) for t in capture.raw_chunks if filter_phantoms(t)),
                        cleaned=cleaned, raw_chunks=capture.raw_chunks, chunk_compute_s=capture.chunk_times,
                        processing_s=end-start if not args.realtime else None,
                        stop_to_text_s=end-stop_time if args.realtime else None,
                        compute_s=sum(capture.chunk_times), stop_call_s=stop_call_s, backlog_at_stop=backlog_at_stop,
                        rtf=sum(capture.chunk_times)/entry["duration_s"],
                        peak_allocated_vram_mb=engine.peak_memory_mb() if hasattr(engine,"peak_memory_mb") else None)
            record["utterances"].append(item)
            write_json(out, record)
            print(f"{args.engine}: clip {i+1}/{len(entries)}, repeat {repeat+1}, compute {item['compute_s']:.3f}s", flush=True)
    record["completed"] = True
    write_json(out, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())

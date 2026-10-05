"""Offline runtime controls around the same app replay, with explicit provenance.

One process, one local model, one bounded corpus. Use an external owned-process
timeout for unattended work. No microphone, clipboard, downloads or new packages.
"""
import argparse
from dataclasses import replace
import inspect
import json
import os
from pathlib import Path
import sys

from asr_trial_common import ROOT, local_result_path, sha256, source_hashes
from whisper_accuracy_ablation import model_integrity
import trial_chunk_window

sys.path.insert(0, str(ROOT / "src"))
import fw_engine
from whisper_decoder_trace import DecoderTrace, numeric_fields, OPTION_FIELDS, MAX_SEGMENTS, MAX_CALLS


def adapter_sources():
    return {p.name: sha256(p) for p in (Path(__file__), Path(trial_chunk_window.__file__),
                                      Path(__file__).with_name("whisper_decoder_trace.py"))}


def configure_decoder(engine, patience, temperature, *, trace=None):
    """Change only selected search controls; preserve all app audio/text handling."""
    original = engine.model.transcribe
    defaults = inspect.signature(original).parameters
    temperatures = defaults["temperature"].default if temperature == "default" else 0.0
    traces = []

    def transcribe(audio, **kwargs):
        kwargs["patience"] = patience if engine.beam_size > 1 else 1.0
        if temperature == "zero":
            kwargs["temperature"] = 0.0
        trace_record = dict(audio_s=len(audio) / 16000, segments=[],
            parameters=numeric_fields(kwargs, OPTION_FIELDS + ("vad_filter",)) if trace else
                       {k: v for k, v in kwargs.items() if k != "initial_prompt"})
        observed = trace.safe("call_sink", lambda: trace.begin(audio, kwargs, kwargs.get("temperature", temperatures))) if trace else None
        if trace is None or len(traces) < MAX_CALLS:
            traces.append(trace_record)
        try:
            segments, info = original(audio, **kwargs)
        except BaseException as error:
            if trace:
                trace.safe("call_error_sink", lambda: trace.end(observed, "recognition_error", error))
            raise
        if trace:
            trace.safe("info_sink", lambda: trace.info(observed, info))

        def tracked():
            try:
                for segment in segments:
                    def legacy():
                        trace_record["segments"].append({k: getattr(segment, k, None) for k in
                            ("temperature", "avg_logprob", "compression_ratio", "no_speech_prob")})
                    if trace:
                        if observed is not None and trace.segment_count < MAX_SEGMENTS:
                            trace.safe("legacy_segment_metadata", legacy)
                        trace.safe("segment_sink", lambda: trace.segment(observed, segment))
                    else:
                        legacy()
                    yield segment
                trace_record["completed"] = True
                if trace:
                    trace.safe("completion_sink", lambda: trace.end(observed, "exhausted"))
            except GeneratorExit:
                if trace:
                    trace.safe("cancel_sink", lambda: trace.end(observed, "cancelled"))
                raise
            except BaseException as error:
                if trace:
                    trace.safe("iteration_error_sink", lambda: trace.end(observed, "recognition_error", error))
                raise

        return tracked(), info

    engine.model.transcribe = transcribe
    return traces, temperatures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path, help="Existing CTranslate2 snapshot")
    parser.add_argument("--compute", choices=("int8_float32", "int8_float16", "float16"), default="int8_float32")
    parser.add_argument("--threads", type=int, choices=(2, 8), default=2)
    parser.add_argument("--beam", type=int, choices=(1, 2, 3, 5), default=5)
    parser.add_argument("--patience", type=float, choices=(1.0, 2.0), default=2.0)
    parser.add_argument("--temperature", choices=("default", "zero"), default="default")
    parser.add_argument("--chunk-seconds", type=int, choices=(20, 30), default=30)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--trace-decoder", action="store_true", help="Bounded public-call trace in the chosen ignored result")
    parser.add_argument("--trace-prompt-text", action="store_true", help="Retain actual prompt text locally; requires --trace-decoder")
    args, replay = parser.parse_known_args(argv)
    if args.trace_prompt_text and not args.trace_decoder:
        parser.error("--trace-prompt-text requires --trace-decoder")
    if "--engine" in replay or "--device" in replay or "--model-path" in replay:
        parser.error("This adapter only runs the specified local Whisper model on CUDA")
    out = local_result_path(args.out)
    if out.exists():
        raise ValueError("Refusing to overwrite a runtime experiment")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    model = model_integrity(args.model)
    sources, adapters = source_hashes(), adapter_sources()
    original_engine = fw_engine.FasterWhisperEngine
    original_write = trial_chunk_window.trial_asr.write_json
    evidence = {}
    decoder_trace = DecoderTrace(args.trace_prompt_text) if args.trace_decoder else None

    def engine_factory(config, **kwargs):
        from faster_whisper import WhisperModel
        selected = replace(config, model=model["path"], compute_type=args.compute,
                           cpu_threads=args.threads, reason="Frozen runtime experiment")
        engine = original_engine(selected,
            model_factory=lambda *a, **k: WhisperModel(*a, local_files_only=True, **k),
            beam_size=args.beam)
        actual = engine.model.model
        if engine.config.device != "cuda" or actual.device != "cuda" or actual.compute_type != args.compute:
            raise ValueError("Device/precision fallback; refusing a mislabeled run")
        traces, temperatures = configure_decoder(engine, args.patience, args.temperature, trace=decoder_trace)
        evidence.update(traces=traces, temperature=temperatures)
        return engine

    def checkpoint(path, record):
        if record.get("completed"):
            if source_hashes() != sources or adapter_sources() != adapters:
                raise ValueError("Source changed during runtime experiment")
            if model_integrity(args.model) != model:
                raise ValueError("Model changed during runtime experiment")
            if not evidence.get("traces") or any(not t.get("completed") for t in evidence["traces"]):
                raise ValueError("Incomplete decoder trace")
        record["runtime_adapter_sha256"] = adapters
        record["model_integrity"] = model
        record["config"].update(model_snapshot=model["path"], compute=args.compute,
            cpu_threads=args.threads, beam=args.beam,
            patience=args.patience if args.beam > 1 else 1.0,
            temperature=evidence.get("temperature"), language="en")
        record["decoder_traces"] = evidence.get("traces", [])
        if decoder_trace:
            snapshot = decoder_trace.safe("snapshot_sink", decoder_trace.snapshot)
            record["decoder_trace"] = snapshot if snapshot is not None else dict(
                schema="whisper-public-decoder-trace-v1", enabled=True, complete=False,
                failures=list(decoder_trace.failures))
        original_write(path, record)

    fw_engine.FasterWhisperEngine = engine_factory
    trial_chunk_window.trial_asr.write_json = checkpoint
    try:
        return trial_chunk_window.main(["--chunk-seconds", str(args.chunk_seconds),
            "--engine", "whisper", "--out", str(out), *replay])
    finally:
        fw_engine.FasterWhisperEngine = original_engine
        trial_chunk_window.trial_asr.write_json = original_write


if __name__ == "__main__":
    raise SystemExit(main())

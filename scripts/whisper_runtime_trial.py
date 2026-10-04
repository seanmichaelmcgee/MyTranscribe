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


def adapter_sources():
    return {p.name: sha256(p) for p in (Path(__file__), Path(trial_chunk_window.__file__))}


def configure_decoder(engine, patience, temperature):
    """Change only selected search controls; preserve all app audio/text handling."""
    original = engine.model.transcribe
    defaults = inspect.signature(original).parameters
    temperatures = defaults["temperature"].default if temperature == "default" else 0.0
    traces = []

    def transcribe(audio, **kwargs):
        kwargs["patience"] = patience if engine.beam_size > 1 else 1.0
        if temperature == "zero":
            kwargs["temperature"] = 0.0
        trace = dict(audio_s=len(audio) / 16000, segments=[],
                     parameters={k: v for k, v in kwargs.items() if k != "initial_prompt"})
        traces.append(trace)
        segments, info = original(audio, **kwargs)

        def tracked():
            for segment in segments:
                trace["segments"].append({k: getattr(segment, k, None) for k in
                    ("temperature", "avg_logprob", "compression_ratio", "no_speech_prob")})
                yield segment
            trace["completed"] = True

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
    args, replay = parser.parse_known_args(argv)
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
        traces, temperatures = configure_decoder(engine, args.patience, args.temperature)
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

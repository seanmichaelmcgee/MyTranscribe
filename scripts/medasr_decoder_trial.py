"""Offline, opt-in MedASR decoder comparisons with verified local logit caching.

Uses the existing app replay and scorer. Cache keys cover waveform, official
weights, runtime and acoustic adapter; decoder experiments never read references.
Saved arrays are loaded with pickle disabled. Outputs stay in ignored results_*.
"""
import argparse
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from asr_trial_common import (ROOT, MODEL_REVISION, canonical_hash, local_result_path,
                              sha256, verify_model, write_json)
from medasr_ctc_decoder import ArpaLanguageModel, prefix_beam_search
from prepare_medasr_lm import LM_ROOT
import trial_asr


class DecoderTrialEngine:
    def __init__(self, model_path, device, precision, args):
        if device != "cuda" or precision != "float32":
            raise ValueError("Decoder trials require the verified CUDA float32 configuration")
        self.provenance = verify_model(model_path)
        self.args = args
        self.cache = local_result_path(args.cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.identity = dict(model=self.provenance, precision=precision,
            engine_source=sha256(ROOT / "src" / "medasr_engine.py"),
            cache_implementation=sha256(Path(__file__)),
            versions={n: importlib.metadata.version(n) for n in ("numpy", "torch", "transformers")})
        if args.cache_only:
            from transformers import AutoProcessor
            self.processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
            self.engine = None
            self.gpu_name = "cache replay: no GPU inference"
        else:
            self.engine = ORIGINAL_ENGINE(model_path, device, precision)
            self.processor = self.engine.processor
            self.gpu_name = self.engine.gpu_name
        tokenizer = self.processor.tokenizer
        self.pieces = [tokenizer.convert_ids_to_tokens(i).replace("\u2581", "#") for i in range(tokenizer.vocab_size)]
        self.lm = ArpaLanguageModel(args.lm) if args.lm is not None else None
        self.decode_times = []

    def logits(self, audio):
        identity = dict(self.identity, waveform_sha256=__import__("hashlib").sha256(audio.tobytes()).hexdigest())
        key = canonical_hash(identity)
        array_path, info_path = self.cache / (key + ".npy"), self.cache / (key + ".json")
        if info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            if info.get("identity") != identity or info.get("sha256") != sha256(array_path):
                raise ValueError("Acoustic cache integrity mismatch")
            result = np.load(array_path, allow_pickle=False)
        else:
            if self.engine is None:
                raise ValueError("Cache miss; run a sequential GPU cache collection first")
            engine = self.engine
            inputs = self.processor(audio=audio.astype(np.float32), sampling_rate=16000, return_tensors="pt", padding=True)
            inputs = {k: v.to(device=engine.device, dtype=engine.model_dtype) if v.is_floating_point()
                      else v.to(engine.device) for k, v in inputs.items()}
            with engine.torch.inference_mode():
                output = engine.model.generate(**inputs, return_dict_in_generate=True)
                from medasr_engine import checked_ctc_sequences
                checked_ctc_sequences(output, engine.torch.isfinite)
                logits = output.logits[0]
                if "attention_mask" in inputs:
                    mask = engine.model._get_output_attention_mask(inputs["attention_mask"], target_length=logits.shape[0])[0]
                    logits = logits[mask]
                result = logits.float().cpu().numpy()
            with array_path.open("wb") as stream:
                np.save(stream, result, allow_pickle=False)
            write_json(info_path, dict(identity=identity, sha256=sha256(array_path)))
        if result.ndim != 2 or result.shape[1] != len(self.pieces) or not np.isfinite(result).all():
            raise ValueError("Invalid cached acoustic logits")
        return result

    def transcribe(self, audio, prompt=None):
        logits = self.logits(audio)
        start = time.perf_counter()
        if self.args.beam == 0:
            ids = logits.argmax(axis=-1).tolist()
            text = self.processor.tokenizer.decode(ids, skip_special_tokens=True, group_tokens=True)
        else:
            ids = prefix_beam_search(logits, beam_width=self.args.beam, token_limit=self.args.token_limit,
                token_logp=self.args.token_logp, lm=self.lm, pieces=self.pieces,
                alpha=self.args.alpha, beta=self.args.beta)
            text = self.processor.tokenizer.decode(ids, skip_special_tokens=True, group_tokens=False)
        self.decode_times.append(time.perf_counter() - start)
        return text.strip()

    def synchronize(self):
        if self.engine:
            self.engine.synchronize()

    def reset_peak_memory(self):
        if self.engine:
            self.engine.reset_peak_memory()

    def peak_memory_mb(self):
        return self.engine.peak_memory_mb() if self.engine else None


ORIGINAL_ENGINE = None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--beam", type=int, default=0)
    parser.add_argument("--alpha", type=float, default=0.0)
    parser.add_argument("--beta", type=float, default=0.0)
    parser.add_argument("--token-limit", type=int, default=16)
    parser.add_argument("--token-logp", type=float, default=-8.0)
    parser.add_argument("--lm", type=Path)
    parser.add_argument("--cache", type=Path, default=ROOT / "results_medasr" / "decoder_logits_20261004")
    parser.add_argument("--cache-only", action="store_true")
    args, replay_args = parser.parse_known_args(argv)
    if not 0 <= args.beam <= 64 or not 1 <= args.token_limit <= 512:
        parser.error("Bounded beam 0..64 and token limit 1..512 required")
    if (args.alpha or args.beta) and not args.beam:
        parser.error("Search weights require a beam")
    if args.alpha and args.lm is None:
        parser.error("LM weight requires a verified local LM index")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    sys.path.insert(0, str(ROOT / "src"))
    import medasr_engine
    global ORIGINAL_ENGINE
    ORIGINAL_ENGINE = medasr_engine.MedASREngine
    holder = []
    def factory(model_path, device, precision):
        engine = DecoderTrialEngine(model_path, device, precision, args)
        holder.append(engine)
        return engine
    medasr_engine.MedASREngine = factory
    try:
        status = trial_asr.main(["--engine", "medasr", *replay_args])
        out = Path(replay_args[replay_args.index("--out") + 1])
        record = json.loads(out.read_text(encoding="utf-8"))
        record["config"].update(decoding="greedy CTC" if not args.beam else "experimental prefix beam CTC",
            beam=args.beam, alpha=args.alpha, beta=args.beta, token_limit=args.token_limit, token_logp=args.token_logp,
            acoustic_cache_only=args.cache_only, lm_sha256=sha256(args.lm) if args.lm else None)
        record["decoder_s"] = holder[0].decode_times
        # Cached runs measure decoder/pipeline work only, never GPU or clinical latency.
        if args.cache_only:
            record["replay"] = "cached acoustic logits: decoder/pipeline only"
            for item in record["utterances"]:
                item["stop_to_text_s"] = None
                item["rtf"] = None
        write_json(out, record)
        return status
    finally:
        medasr_engine.MedASREngine = ORIGINAL_ENGINE
        for engine in holder:
            if engine.lm:
                engine.lm.close()


if __name__ == "__main__":
    sys.exit(main())

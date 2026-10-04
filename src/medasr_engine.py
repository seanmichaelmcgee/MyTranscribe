"""Experimental local MedASR adapter. The production Whisper GUI never imports this.

Input: mono 16 kHz float32 in [-1, 1]. Caller uses the existing ~20 s
pause-cut chunks. Greedy CTC, no external language model or vocabulary prompt.
Only a verified local official snapshot is accepted; remote code is disabled.
"""
import os
import sys
from pathlib import Path

import numpy as np


class MedASREngine:
    def __init__(self, model_path: Path, device: str = "cuda", precision: str = "float32"):
        if device not in ("cuda", "cpu") or precision not in ("float32", "float16"):
            raise ValueError("Unsupported device/precision")
        if device == "cpu" and precision != "float32":
            raise ValueError("CPU trials use float32")
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from asr_trial_common import verify_model
        self.provenance = verify_model(model_path)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from transformers import AutoModelForCTC, AutoProcessor
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but unavailable; choose --device cpu explicitly")
        self.torch, self.device, self.precision = torch, device, precision
        self.processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True,
                                                      trust_remote_code=False)
        dtype = torch.float16 if precision == "float16" else torch.float32
        self.model = AutoModelForCTC.from_pretrained(
            str(model_path), local_files_only=True, trust_remote_code=False,
            use_safetensors=True, dtype=dtype, attn_implementation="eager").to(device).eval()
        self.model_dtype = dtype
        self.gpu_name = torch.cuda.get_device_name(0) if device == "cuda" else None

    def transcribe(self, audio: np.ndarray, prompt=None) -> str:
        # MedASR CTC has no Whisper-style initial_prompt; never feed references.
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError("Expected finite mono waveform")
        if audio.size == 0:
            return ""
        inputs = self.processor(audio=audio.astype(np.float32), sampling_rate=16000,
                                return_tensors="pt", padding=True)
        inputs = {k: v.to(device=self.device, dtype=self.model_dtype) if v.is_floating_point()
                  else v.to(self.device) for k, v in inputs.items()}
        with self.torch.inference_mode():
            tokens = self.model.generate(**inputs)
        return self.processor.batch_decode(tokens, skip_special_tokens=True)[0].strip()

    def synchronize(self):
        if self.device == "cuda":
            self.torch.cuda.synchronize()

    def reset_peak_memory(self):
        if self.device == "cuda":
            self.torch.cuda.reset_peak_memory_stats()

    def peak_memory_mb(self):
        if self.device == "cuda":
            return self.torch.cuda.max_memory_allocated() / 2**20
        return None

"""Experimental local MedASR adapter. The production Whisper GUI never imports this.

Input: mono 16 kHz float32 in [-1, 1]. Caller uses the existing ~20 s
pause-cut chunks. Greedy CTC, no external language model or vocabulary prompt.
Only a verified local official snapshot is accepted; remote code is disabled.
"""
import os
import sys
from pathlib import Path

import numpy as np


def checked_ctc_sequences(output, isfinite):
    """NaN/Inf logits can argmax to blanks; never report that as a successful decode."""
    if not isfinite(output.logits).all():
        raise RuntimeError("MedASR produced nonfinite logits; reject this precision/runtime configuration")
    return output.sequences


def spoken_markers(text: str) -> str:
    """
    MedASR writes dictated formatting as brace markers ("{period}", "{comma}",
    "{new paragraph}", "{newline}"). Turn them back into the spoken words so the
    app's own command handling (voice_commands) formats them like any engine's.
    """
    import re
    # A section heading comes out as "[MEDICATION REVIEW]": write it "Medication review:".
    text = re.sub(r"\[([A-Z][A-Z /&-]{2,60})\]", lambda m: m.group(1).capitalize() + ":", text)
    text = re.sub(r"\{\s*newline\s*\}", "{new line}", text, flags=re.I)
    text = re.sub(r"\s*\{([^{}]+)\}\s*", lambda m: f" {m.group(1).strip()}, ", text)   # set off, as a command
    text = re.sub(r"[{}]", " ", text)                       # half a marker left by a chunk edge
    text = re.sub(r"\s+,", ",", re.sub(r",(\s*,)+", ",", text))
    return re.sub(r"[ 	]{2,}", " ", text).strip(" ,")


class MedASREngine:
    writes_marker_words = True      # dictated marks arrive as words: always convert them

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
        from types import SimpleNamespace
        self.pad_s = float(os.environ.get("MYTRANSCRIBE_MEDASR_PAD_S", "0.3"))
        self.config = SimpleNamespace(model=str(model_path), device=device, compute_type=precision)

    def transcribe(self, audio: np.ndarray, prompt=None) -> str:
        # MedASR CTC has no Whisper-style initial_prompt; never feed references.
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError("Expected finite mono waveform")
        if audio.size == 0:
            return ""
        if self.pad_s > 0:
            # The model garbles the first words and drops the last ones when speech
            # touches the edge of its input; a little silence on both sides fixes most of it.
            n = int(self.pad_s * 16000)
            noise = np.random.default_rng(0).normal(0, 3e-4, 2 * n).astype(np.float32)   # about -70 dBFS
            audio = np.concatenate([noise[:n], audio.astype(np.float32), noise[n:]])
        inputs = self.processor(audio=audio.astype(np.float32), sampling_rate=16000,
                                return_tensors="pt", padding=True)
        inputs = {k: v.to(device=self.device, dtype=self.model_dtype) if v.is_floating_point()
                  else v.to(self.device) for k, v in inputs.items()}
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, return_dict_in_generate=True)
            tokens = checked_ctc_sequences(output, self.torch.isfinite)
        return spoken_markers(self.processor.batch_decode(tokens, skip_special_tokens=True)[0])

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

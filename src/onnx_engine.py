"""
onnx_engine.py — experimental recognisers that run through onnx-asr.

NVIDIA Parakeet TDT 0.6B v2 and Canary 1B v2 as ONNX exports (community
conversions on Hugging Face, loaded by the onnx-asr package). Trial code: the
app's default engine is still faster-whisper, and nothing here is imported
unless this engine is asked for. Needs a separate environment with
`onnxruntime-gpu` and `onnx-asr[hub]`; see docs/optimization.

Same contract as FasterWhisperEngine where the pipeline needs it:

    transcribe(audio, prompt)        -> text          (prompt is ignored: these
                                                       models take no vocabulary prompt)
    transcribe_words(audio, prompt)  -> [(word, start_s, end_s)]  (Parakeet only)

Audio: mono float32 in [-1, 1] at 16 kHz, one ~24-30 s chunk at a time.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger("onnx_engine")
SAMPLE_RATE = 16000
MODELS = {"parakeet": "nemo-parakeet-tdt-0.6b-v2", "parakeet-v3": "nemo-parakeet-tdt-0.6b-v3",
          "canary": "nemo-canary-1b-v2"}
FRAME_S = 0.08          # one encoder frame; a token's end is taken as the next token's start


@dataclass
class OnnxConfig:
    model: str
    device: str
    compute_type: str = "float32"


class OnnxAsrEngine:
    def __init__(self, name: str = "parakeet", device: str = "cuda", model=None) -> None:
        self.config = OnnxConfig(MODELS.get(name, name), device)
        if model is None:
            import onnxruntime as ort
            import onnx_asr
            if device == "cuda" and hasattr(ort, "preload_dlls"):
                ort.preload_dlls()                       # CUDA/cuDNN from the pip wheels
            providers = (["CUDAExecutionProvider"] if device == "cuda" else []) + ["CPUExecutionProvider"]
            options = ort.SessionOptions()
            options.log_severity_level = 3
            model = onnx_asr.load_model(self.config.model, providers=providers, sess_options=options)
        self.model = model
        self._timed = model.with_timestamps() if hasattr(model, "with_timestamps") else None
        self._kwargs = {"language": "en"} if "canary" in self.config.model else {}
        if self._timed is not None and "canary" not in self.config.model:
            self.transcribe_words = self._transcribe_words   # the pipeline checks hasattr()

    def transcribe(self, audio: np.ndarray, prompt: Optional[str] = None) -> str:
        if audio.size == 0:
            return ""
        return str(self.model.recognize(audio.astype(np.float32), sample_rate=SAMPLE_RATE, **self._kwargs)).strip()

    def _transcribe_words(self, audio: np.ndarray, prompt: Optional[str] = None, quick: bool = False) -> list:
        """[(word, start_s, end_s)], plus a probability as fourth value when quick=True."""
        if audio.size == 0:
            return []
        result = self._timed.recognize(audio.astype(np.float32), sample_rate=SAMPLE_RATE, **self._kwargs)
        return words_from_tokens(result.tokens, result.timestamps, getattr(result, "logprobs", None),
                                 len(audio) / SAMPLE_RATE, with_probability=quick)

    def count_tokens(self, text: str) -> int:
        return int(len(text) / 2.8) + 1

    def warmup(self) -> None:
        try:
            self.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))
        except Exception as exc:                          # warm-up is best effort
            logger.warning("Warmup skipped: %s", exc)


def words_from_tokens(tokens, starts, logprobs, audio_s: float, with_probability: bool = False) -> list:
    """
    Group sub-word tokens into words. A token that begins with a space starts a
    word; the word keeps its leading space, as faster-whisper's words do, so
    "".join(word for word, ...) is the text.
    """
    words = []
    for i, (token, start) in enumerate(zip(tokens, starts)):
        end = min(audio_s, starts[i + 1] if i + 1 < len(starts) else start + FRAME_S)
        prob = float(np.exp(logprobs[i])) if logprobs is not None and i < len(logprobs) else 1.0
        if token.startswith(" ") or not words:
            words.append([token if token.startswith(" ") else " " + token, float(start), float(end), prob])
        else:
            words[-1][0] += token
            words[-1][2] = float(end)
            words[-1][3] = min(words[-1][3], prob)
    return [tuple(w) if with_probability else tuple(w[:3]) for w in words]

"""
fw_engine.py — thin wrapper around faster-whisper (CTranslate2 backend).

Why faster-whisper instead of openai-whisper for the GTX 1060 edition:
  * int8 weights: large-v3-turbo fits in ~1.6 GB VRAM instead of ~6 GB.
  * No PyTorch dependency (saves ~2.5 GB of install, and avoids the
    torch-version / Pascal (sm_61) support question entirely).
  * Built-in Silero VAD drops silence before decoding, which removes most of
    the "Thank you for watching" style hallucinations at the source.
  * Takes a numpy array directly, so audio never touches the disk (PHI).

The engine is deliberately tiny: transcribe(float32 audio, prompt) -> str.
That is the only surface ChunkedTranscriber depends on, so tests swap in a
fake engine and never need a model.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np

from hw_profile import EngineConfig

logger = logging.getLogger("fw_engine")

SAMPLE_RATE = 16000

# Decoding settings. beam_size=5 is faster-whisper's default and noticeably
# more accurate on drug names than greedy; $MYTRANSCRIBE_BEAM_SIZE=1 trades
# accuracy for ~2x speed if the 1060 turns out to be too slow.
DEFAULT_BEAM_SIZE = 5
VAD_PARAMETERS = {
    # Dictation has short thinking pauses; keep them inside one segment.
    "min_silence_duration_ms": 700,
    "speech_pad_ms": 300,
}


def register_cuda_dll_dirs(
    search_paths: Optional[Iterable[str]] = None,
    add_dll_directory: Optional[Callable] = None,
    platform: str = sys.platform,
) -> list:
    """
    Windows only: make pip-installed CUDA libraries (nvidia-cublas-cu12,
    nvidia-cudnn-cu12) visible to CTranslate2.

    Those wheels put DLLs in <site-packages>/nvidia/<lib>/bin, which Windows'
    loader does not search. Must run before `import ctranslate2` loads CUDA.
    Returns the directories that were added (for logging / tests).
    """
    if platform != "win32":
        return []
    if search_paths is None:
        search_paths = sys.path
    if add_dll_directory is None:
        add_dll_directory = getattr(os, "add_dll_directory", None)
    added = []
    for base in search_paths:
        nvidia_root = Path(base) / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for bin_dir in sorted(nvidia_root.glob("*/bin")):
            if not bin_dir.is_dir():
                continue
            try:
                if add_dll_directory is not None:
                    add_dll_directory(str(bin_dir))
                # Some CTranslate2 builds resolve cuDNN via PATH instead.
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                added.append(str(bin_dir))
            except OSError as exc:
                logger.warning("Could not add DLL dir %s: %s", bin_dir, exc)
    return added


class FasterWhisperEngine:
    """
    Owns one faster-whisper WhisperModel.

    Parameters
    ----------
    config : EngineConfig
        Model name/path, device, compute type, CPU threads.
    model_factory : callable, optional
        Injectable for tests; defaults to faster_whisper.WhisperModel.
    beam_size : int, optional
        Overrides $MYTRANSCRIBE_BEAM_SIZE / DEFAULT_BEAM_SIZE.
    """

    def __init__(self, config: EngineConfig, model_factory: Optional[Callable] = None,
                 beam_size: Optional[int] = None) -> None:
        self.config = config
        if beam_size is None:
            try:
                beam_size = int(os.environ.get("MYTRANSCRIBE_BEAM_SIZE", DEFAULT_BEAM_SIZE))
            except ValueError:
                beam_size = DEFAULT_BEAM_SIZE
        self.beam_size = max(1, beam_size)

        if model_factory is None:
            from faster_whisper import WhisperModel
            model_factory = WhisperModel

        t0 = time.perf_counter()
        self.model = self._load(model_factory, config)
        self.load_seconds = time.perf_counter() - t0
        logger.info(
            "Loaded model '%s' on %s (%s) in %.1fs [%s]",
            self.config.model, self.config.device, self.config.compute_type,
            self.load_seconds, self.config.reason,
        )

    def _load(self, model_factory: Callable, config: EngineConfig):
        """Load the model; if CUDA init fails (driver/DLL issues), fall back to CPU."""
        try:
            return model_factory(
                config.model,
                device=config.device,
                compute_type=config.compute_type,
                cpu_threads=config.cpu_threads,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            if config.device != "cuda":
                raise
            logger.error("CUDA model load failed (%s); falling back to CPU int8", exc)
            self.config = EngineConfig(
                model=config.model, device="cpu", compute_type="int8",
                cpu_threads=max(1, (os.cpu_count() or 2) - 1),
                reason=f"CUDA load failed: {exc}",
            )
            return model_factory(
                self.config.model,
                device="cpu",
                compute_type="int8",
                cpu_threads=self.config.cpu_threads,
            )

    def transcribe(self, audio: np.ndarray, prompt: Optional[str] = None) -> str:
        """
        Transcribe mono float32 16 kHz audio in [-1, 1]. Returns plain text.

        condition_on_previous_text=False: within one chunk, don't let a
        mis-heard sentence bias the next one (the original app's anti-
        hallucination setting). Cross-chunk context comes from `prompt`.
        """
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        segments, _info = self.model.transcribe(
            audio,
            language="en",
            task="transcribe",
            beam_size=self.beam_size,
            initial_prompt=prompt or None,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=VAD_PARAMETERS,
            without_timestamps=True,
        )
        # segments is a lazy generator: decoding happens while we iterate.
        return " ".join(s.text.strip() for s in segments if s.text.strip())

    def count_tokens(self, text: str) -> int:
        """Exact Whisper token count (for prompt budgeting); estimate if unavailable."""
        tok = getattr(self.model, "hf_tokenizer", None)
        if tok is None:
            return int(len(text) / 2.8) + 1
        return len(tok.encode(" " + text.strip(), add_special_tokens=False).ids)

    def warmup(self) -> None:
        """Run one tiny inference so CUDA kernels/allocator are ready before first use."""
        try:
            t0 = time.perf_counter()
            # VAD off: with it on, silence never reaches the encoder and nothing warms.
            # Output (likely empty or junk) is discarded; max_new_tokens bounds the time.
            segments, _ = self.model.transcribe(
                np.zeros(SAMPLE_RATE, dtype=np.float32),
                language="en", beam_size=1, vad_filter=False,
                without_timestamps=True, max_new_tokens=8,
            )
            for _ in segments:
                pass
            logger.info("Warmup done in %.2fs", time.perf_counter() - t0)
        except Exception as exc:
            logger.warning("Warmup skipped: %s", exc)

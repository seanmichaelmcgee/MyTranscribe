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

# Decoding settings: beam search, 5 beams, patience 2.
# On the user's REAL recordings (2026-10-03, 30 clips, names ignored) greedy
# decoding doubled medical-word errors (12.4 % vs 8.2 %) and tripled invented
# words (1.5 vs 0.9 per 100) compared with beam 5. (Synthetic TTS voices had
# suggested greedy was as good: they are too clean to show it.) Plain beam 5
# sometimes drops spoken commands ("new line") as if they were filler; patience
# 2 (keep searching for more finished hypotheses) restored them: messages with
# correct formatting 20/24 -> 23/24, no accuracy cost, ~+0.1 s.
# $MYTRANSCRIBE_BEAM_SIZE=1 trades accuracy for speed.
DEFAULT_BEAM_SIZE = 5
DEFAULT_PATIENCE = 2.0
# Processor only (no usable NVIDIA card; small.en): 3 beams, patience 1. On the owner's 47
# real recordings (2026-11-19) this kept beam 5's accuracy (9.98% word errors, 36 of 314
# medical words wrong; greedy: 10.48%, 43 of 314) and, on four laptop-class cores, cut a 7.5 s
# message from 4.8 s to 3.3 s and 30 s of speech from 7.2 s to 5.7 s. With more than one beam
# the vocabulary prompt is what costs time, and patience 2 doubles that.
CPU_BEAM_SIZE = 3
CPU_PATIENCE = 1.0
# Runaway guard: Whisper can loop ("thank you. thank you. ...") or, with
# temperature fallback, decode garbage until the 448-token window is full. A
# chunk never needs more than ~10 tokens per second of audio (fast dictation is
# ~4-6), so cap output to that, within the window left after the prompt.
MAX_TOKENS_PER_SECOND = 10
MIN_NEW_TOKENS = 24
WHISPER_MAX_LENGTH = 448          # decoder window: prompt + special tokens + output
WHISPER_PROMPT_TOKEN_LIMIT = WHISPER_MAX_LENGTH // 2 - 1  # faster-whisper's retained suffix
FRAMES_PER_SECOND = 100           # Whisper feature frames; Segment.seek is in these
WINDOW_FRAMES = 3000              # one 30 s decoding window
WINDOW_SECONDS = 30.0
TAIL_REDECODE_MIN_S = 2.0         # transcribe_words: undecoded audio worth a second look
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


TAIL_SPEECH_MIN_S = 0.3           # sound after the last word that may still be an unheard word
TAIL_FLOOR_RMS = 80 / 32768       # never call quieter than this speech (the app's fixed threshold)


def speech_after(audio: np.ndarray, t: float) -> bool:
    """
    Whether the audio after `t` seconds holds enough sound to be speech: at least
    TAIL_SPEECH_MIN_S of 50 ms frames 12 dB over the clip's own noise floor (its quietest
    tenth of frames). Trailing silence, a breath or a click is not.
    """
    win = SAMPLE_RATE // 20
    usable = (audio.size // win) * win
    if usable == 0:
        return False
    rms = np.sqrt(np.mean(np.square(audio[:usable].astype(np.float32).reshape(-1, win)), axis=1))
    level = max(TAIL_FLOOR_RMS, 4.0 * float(np.percentile(rms, 10)))
    rest = rms[int(t * 20):]
    return float(np.count_nonzero(rest >= level)) / 20 >= TAIL_SPEECH_MIN_S


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
        # Extra keyword arguments for model.transcribe (they win over the defaults
        # below). Empty in the classic pipeline; the dictation candidate and the
        # trial scripts set it, e.g. {"vad_parameters": {...}} or {"vad_filter": False}.
        self.decode_overrides: dict = {}
        self.language = "en"            # Whisper language code; Options -> Dictation language sets it
        on_cpu = config.device == "cpu"
        default_beam = CPU_BEAM_SIZE if on_cpu else DEFAULT_BEAM_SIZE
        if beam_size is None:
            try:
                beam_size = int(os.environ.get("MYTRANSCRIBE_BEAM_SIZE", default_beam))
            except ValueError:
                beam_size = default_beam
        self.beam_size = max(1, beam_size)
        self.patience = CPU_PATIENCE if on_cpu else DEFAULT_PATIENCE

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
                cpu_threads=max(1, min(8, (os.cpu_count() or 2) // 2)),
                reason=f"CUDA load failed: {exc}",
            )
            self.patience = CPU_PATIENCE
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
        segments, _info = self._decode(audio, prompt, {})
        # segments is a lazy generator: decoding happens while we iterate.
        return " ".join(s.text.strip() for s in segments if s.text.strip())

    def transcribe_words(self, audio: np.ndarray, prompt: Optional[str] = None,
                         quick: bool = False) -> list:
        """
        Like transcribe(), but returns [(word, start_s, end_s)] timed against
        `audio` (VAD-removed silence is mapped back by faster-whisper).

        quick=True decodes greedily (no beam search): several times faster, for
        a second listen to a second or two of audio where only a spoken command
        is of interest, not for dictation text. Quick words carry a fourth
        value, the model's probability for the word (0..1).
        """
        extra = {"word_timestamps": True}
        if quick:
            extra.update(beam_size=1, patience=1.0, temperature=0.0)   # one pass, no fallback retries
        audio_s = len(audio) / SAMPLE_RATE
        segments, info = self._decode(audio, prompt, extra)
        heard_s = float(getattr(info, "duration_after_vad", audio_s))
        words, window = [], None
        for s in segments:
            seek = getattr(s, "seek", 0)
            if window is not None and seek != window:
                # With word timings faster-whisper decodes again from the last word's
                # end. After a full 30 s window that is the next window. Otherwise it
                # is the few tenths of a second left over, which only ever yields
                # "Thank you." or a repeat of the last word: stop there, unless enough
                # audio is left that the model plainly stopped early.
                full_window = seek - window >= WINDOW_FRAMES - 10
                if not full_window and heard_s - seek / FRAMES_PER_SECOND < TAIL_REDECODE_MIN_S:
                    break
            window = seek
            if quick:
                words += [(w.word, float(w.start), float(w.end), float(getattr(w, "probability", 1.0)))
                          for w in (s.words or [])]
            else:
                words += [(w.word, float(w.start), float(w.end)) for w in (s.words or [])]
            if audio_s <= WINDOW_SECONDS and words and (audio_s - words[-1][2] < TAIL_REDECODE_MIN_S
                                                        or not speech_after(audio, words[-1][2])):
                # Nothing left worth decoding: don't even ask. Asking costs a whole window: on a
                # processor, a 25 s piece that ended in 3 s of silence took 11 s instead of 5.
                break
        return words

    def _decode(self, audio: np.ndarray, prompt: Optional[str], extra: dict):
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        kwargs = dict(
            language=self.language,
            task="transcribe",
            beam_size=self.beam_size,
            patience=self.patience if self.beam_size > 1 else 1.0,
            initial_prompt=prompt or None,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=VAD_PARAMETERS,
            without_timestamps=True,
            max_new_tokens=self.max_new_tokens(len(audio) / SAMPLE_RATE, prompt),
        )
        kwargs.update(self.decode_overrides)
        kwargs.update(extra)
        return self.model.transcribe(audio, **kwargs)

    def max_new_tokens(self, audio_s: float, prompt: Optional[str]) -> int:
        """Output cap for one chunk: proportional to its length, within the decoder window."""
        # faster-whisper discards prompt tokens beyond its 223-token suffix.
        # Counting the discarded text could wrongly shrink the output cap to 24
        # and truncate a letter when a long personal style file is supplied.
        prompt_tokens = min(self.count_tokens(prompt), WHISPER_PROMPT_TOKEN_LIMIT) + 1 if prompt else 0
        room = WHISPER_MAX_LENGTH - prompt_tokens - 4                       # sot, lang, task, notimestamps
        want = int(audio_s * MAX_TOKENS_PER_SECOND) + MIN_NEW_TOKENS
        return max(MIN_NEW_TOKENS, min(want, room))

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

"""
chunked_transcriber.py — background, in-memory transcription for long dictation.

Replaces transcriber_v12.RealTimeTranscriber in the 1060 edition. Differences:

  * Audio stays in RAM (numpy), never written to a temp WAV (PHI on disk).
  * Two threads per session:
      capture thread  reads the mic, cuts the audio into ~30 s chunks at the
                      quietest moment near the target length (so words are
                      not split), and queues them;
      worker thread   transcribes queued chunks in order.
    So a 10-minute letter is mostly transcribed *while you are still talking*;
    pressing Stop only waits for the last chunk, and the GUI never blocks.
  * Chunks are joined with spaces, not newlines (they are mid-paragraph cuts).
  * The hallucination filter only drops a chunk that is *entirely* a known
    phantom phrase, so a letter that genuinely starts "Thank you for seeing..."
    is kept (transcriber_v12 stripped the leading "Thank you").

Audio format (CLAUDE.md: document chunk size/format/rate):
  capture: 16 kHz, mono, int16 (paInt16), FRAMES_PER_BUFFER = 1024 samples (64 ms)
  chunks : float32 in [-1, 1], target CHUNK_TARGET_S = 30 s, cut point chosen
           as the lowest-energy 30 ms frame within the last CUT_SEARCH_S = 5 s
  memory : 32 KB/s while buffered -> 1 h session = ~115 MB worst case
"""

import logging
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

logger = logging.getLogger("chunked_transcriber")

SAMPLE_RATE = 16000
FRAMES_PER_BUFFER = 1024          # 64 ms per read
BYTES_PER_SAMPLE = 2              # int16
CHUNK_TARGET_S = 30.0             # Whisper's native window is 30 s
CUT_SEARCH_S = 5.0                # look this far back for a pause to cut at
CUT_FRAME_MS = 30                 # energy window for finding the pause
MAX_SESSION_S = 60 * 60           # hard cap: 1 hour per recording
LEVEL_THRESHOLD_RMS = 80          # int16 RMS; same as transcriber_v12 (catches whispers)
INDICATOR_HOLD_READS = 10         # keep level indicator lit ~640 ms after speech
PROMPT_TAIL_CHARS = 200           # previous-chunk text fed forward as context
MAX_CONSECUTIVE_READ_ERRORS = 50  # ~ mic unplugged -> end the session cleanly
ERROR_PREFIX = "[Transcription Error:"

# A chunk whose whole text is one of these is a Whisper phantom, not dictation.
_PHANTOM_CHUNKS = {
    "thank you", "thanks", "thank you very much", "thank you for watching",
    "thanks for watching", "you", "bye", "bye bye", "okay", "so",
    "please subscribe", "subtitles by the amara org community",
}
# Trailing YouTube-isms that never occur in clinical dictation.
_PHANTOM_TAIL_RE = re.compile(
    r"[\s.,!]*(thanks? (you )?for watching|please (like and )?subscribe)[\s.!]*$",
    re.IGNORECASE,
)


# ── Pure helpers (unit-tested directly) ──────────────────────────────────────
def int16_bytes_to_float32(data: bytes) -> np.ndarray:
    """PCM int16 little-endian bytes -> float32 in [-1, 1)."""
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def rms_int16(data: bytes) -> float:
    """RMS of int16 PCM bytes, in int16 units (0..32768). Empty -> 0."""
    a = np.frombuffer(data, dtype=np.int16)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(a.astype(np.float32)))))


def find_cut_index(samples: np.ndarray, sample_rate: int = SAMPLE_RATE,
                   search_s: float = CUT_SEARCH_S, frame_ms: int = CUT_FRAME_MS) -> int:
    """
    Return the sample index at which to split `samples`: the centre of the
    quietest frame_ms window within the final search_s seconds. If the buffer
    is shorter than one frame, cut at the end.
    """
    n = len(samples)
    frame = max(1, int(sample_rate * frame_ms / 1000))
    if n < frame:
        return n
    start = max(0, n - int(sample_rate * search_s))
    region = samples[start:n]
    usable = (len(region) // frame) * frame
    if usable == 0:
        return n
    frames = region[len(region) - usable:].reshape(-1, frame).astype(np.float32)
    energy = np.mean(np.square(frames), axis=1)
    # Prefer the latest of equally quiet frames: keeps chunks close to target length.
    quietest = len(energy) - 1 - int(np.argmin(energy[::-1]))
    offset = start + (len(region) - usable)
    return offset + quietest * frame + frame // 2


def chunk_is_silent(samples: np.ndarray, threshold_rms: float = LEVEL_THRESHOLD_RMS) -> bool:
    """True if a float32 chunk's RMS (in int16 units) is below the threshold."""
    if samples.size == 0:
        return True
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32))))) * 32768.0
    return rms < threshold_rms


def filter_phantoms(text: str) -> str:
    """Drop chunks that are entirely a phantom phrase; trim trailing YouTube-isms."""
    if not text:
        return ""
    norm = " ".join(re.sub(r"[^a-z]+", " ", text.lower()).split())
    if norm in _PHANTOM_CHUNKS:
        return ""
    return _PHANTOM_TAIL_RE.sub("", text).strip()


def build_prompt(base_prompt: str, previous_text: str, tail_chars: int = PROMPT_TAIL_CHARS) -> str:
    """
    Vocabulary prompt + the end of what was already transcribed.

    faster-whisper keeps the *last* ~223 tokens of the prompt, so the recent
    context goes at the end and the start of a long vocabulary list is what
    gets trimmed first.
    """
    tail = previous_text[-tail_chars:].strip() if previous_text else ""
    if tail and len(previous_text) > tail_chars:
        # Don't start mid-word.
        space = tail.find(" ")
        if 0 <= space < 30:
            tail = tail[space + 1:]
    return " ".join(p for p in (base_prompt.strip(), tail) if p)


@dataclass
class ChunkStat:
    """Timing for one transcribed chunk (used by benchmarks / stress tests)."""
    audio_s: float
    elapsed_s: float
    chars: int

    @property
    def rtf(self) -> float:
        """Real-time factor: seconds of compute per second of audio (<1 = faster than live)."""
        return self.elapsed_s / self.audio_s if self.audio_s else 0.0


def _default_stream_factory():
    """Open the default microphone with PyAudio. Returns (stream, pyaudio_instance)."""
    import pyaudio
    pa = pyaudio.PyAudio()
    try:
        info = pa.get_default_input_device_info()
        logger.info("Input device [%s] index=%s", info.get("name"), info.get("index"))
    except (IOError, OSError) as exc:
        logger.warning("Could not query default input device: %s", exc)
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                     input=True, frames_per_buffer=FRAMES_PER_BUFFER)
    return stream, pa


class ChunkedTranscriber:
    """
    Records from a stream and transcribes in the background.

    GUI-facing attributes (read lock-free from the GUI thread, like
    RealTimeTranscriber): transcriptions (list[str]), audio_detected (bool).

    Parameters
    ----------
    engine : object with transcribe(np.ndarray float32, prompt: str) -> str
    base_prompt : str
        Vocabulary/style prompt (see prompts/medical_prompt.txt).
    stream_factory : callable returning (stream, owner_or_None)
        stream needs read(n, exception_on_overflow=False), stop_stream(), close().
        Injected by tests and the stress harness.
    """

    def __init__(self, engine, base_prompt: str = "",
                 stream_factory: Optional[Callable] = None,
                 chunk_target_s: float = CHUNK_TARGET_S,
                 cut_search_s: float = CUT_SEARCH_S,
                 max_session_s: float = MAX_SESSION_S,
                 level_threshold_rms: float = LEVEL_THRESHOLD_RMS) -> None:
        self.engine = engine
        self.base_prompt = base_prompt
        self._stream_factory = stream_factory or _default_stream_factory
        self.chunk_target_s = chunk_target_s
        self.cut_search_s = min(cut_search_s, chunk_target_s / 2)
        self.max_session_s = max_session_s
        self.level_threshold_rms = level_threshold_rms

        self.transcriptions: List[str] = []
        self.chunk_stats: List[ChunkStat] = []
        self.audio_detected = False
        self.auto_stopped = False        # True if max_session_s or mic failure ended capture
        self.capture_error: Optional[str] = None
        self.long_mode = False

        self._running = False
        self._indicator_hold = 0
        self._buffer = bytearray()
        self._captured_samples = 0
        self._queue: "queue.Queue[Optional[np.ndarray]]" = queue.Queue()
        self._stream = None
        self._stream_owner = None
        self._capture_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()   # stop_recording finished (remainder queued)

    # ── Public API ───────────────────────────────────────────────────────────
    @property
    def recording(self) -> bool:
        """True while the capture thread is reading the microphone."""
        return self._running

    @property
    def busy(self) -> bool:
        """True while any queued audio is still being transcribed."""
        return self._worker_thread is not None and self._worker_thread.is_alive()

    @property
    def text(self) -> str:
        return " ".join(t for t in self.transcriptions if t)

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    def start_recording(self, mode: str = "normal") -> None:
        """Open the mic and start the capture + worker threads for a new session."""
        if self._running or self.busy:
            raise RuntimeError("previous session still active")
        self.long_mode = (mode == "long")
        self.transcriptions = []
        self.chunk_stats = []
        self.auto_stopped = False
        self.capture_error = None
        self._buffer = bytearray()
        self._captured_samples = 0
        self._queue = queue.Queue()
        self._stopped.clear()

        self._stream, self._stream_owner = self._stream_factory()
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, name="fw-worker", daemon=True)
        self._capture_thread = threading.Thread(target=self._capture_loop, name="fw-capture", daemon=True)
        self._worker_thread.start()
        self._capture_thread.start()

    def stop_recording(self) -> None:
        """
        Stop capturing and queue whatever audio is left. Returns quickly
        (at most one mic read, ~64 ms); transcription continues in the
        background — poll `busy` or call wait_until_idle().
        """
        if self._stopped.is_set():
            return
        self._running = False
        if self._capture_thread is not None and self._capture_thread is not threading.current_thread():
            self._capture_thread.join(timeout=2.0)
            if self._capture_thread.is_alive():
                logger.warning("Capture thread did not exit within 2 s")
        self._close_stream()
        # Capture thread has exited, so the buffer is ours now.
        if self._buffer:
            self._enqueue(bytes(self._buffer))
            self._buffer = bytearray()
        self._queue.put(None)            # sentinel: worker exits after draining
        self.audio_detected = False
        self._indicator_hold = 0
        self._stopped.set()

    def force_process_partial_frames(self) -> None:
        """Compatibility no-op: stop_recording() already flushes the remainder."""

    def wait_until_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until all queued audio is transcribed. Returns False on timeout."""
        if self._worker_thread is None:
            return True
        self._worker_thread.join(timeout)
        return not self._worker_thread.is_alive()

    def cleanup(self) -> None:
        """Stop everything; used on app shutdown. Does not wait for transcription."""
        if self._running or (self._stream is not None and not self._stopped.is_set()):
            self.stop_recording()

    # ── Threads ──────────────────────────────────────────────────────────────
    def _capture_loop(self) -> None:
        target_bytes = int(self.chunk_target_s * SAMPLE_RATE) * BYTES_PER_SAMPLE
        max_samples = int(self.max_session_s * SAMPLE_RATE)
        errors = 0
        while self._running:
            try:
                data = self._stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
                errors = 0
            except Exception as exc:          # PyAudio raises plain OSError/IOError
                errors += 1
                if errors >= MAX_CONSECUTIVE_READ_ERRORS:
                    self.capture_error = f"microphone read failed: {exc}"
                    logger.error("Ending session: %s", self.capture_error)
                    self.auto_stopped = True
                    self._running = False
                    break
                time.sleep(0.01)
                continue
            if not data:
                # End of a finite (test/stress) stream.
                self.auto_stopped = True
                self._running = False
                break
            self._update_level(data)
            self._buffer.extend(data)
            self._captured_samples += len(data) // BYTES_PER_SAMPLE
            if len(self._buffer) >= target_bytes:
                self._cut_and_enqueue()
            if self._captured_samples >= max_samples:
                logger.info("Session reached %.0f s cap; stopping capture", self.max_session_s)
                self.auto_stopped = True
                self._running = False

    def _cut_and_enqueue(self) -> None:
        samples = np.frombuffer(bytes(self._buffer), dtype=np.int16)
        cut = find_cut_index(samples, search_s=self.cut_search_s)
        cut_bytes = cut * BYTES_PER_SAMPLE
        head = bytes(self._buffer[:cut_bytes])
        self._buffer = bytearray(self._buffer[cut_bytes:])
        self._enqueue(head)

    def _enqueue(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._queue.put(int16_bytes_to_float32(pcm))
        depth = self._queue.qsize()
        if depth >= 3:
            logger.warning("Transcription is falling behind: %d chunks queued", depth)

    def _worker_loop(self) -> None:
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            self._transcribe_chunk(chunk)

    def _transcribe_chunk(self, chunk: np.ndarray) -> None:
        audio_s = len(chunk) / SAMPLE_RATE
        if chunk_is_silent(chunk, self.level_threshold_rms):
            logger.info("Skipping silent chunk (%.1fs)", audio_s)
            return
        # Context = previous good text only; never prime Whisper with error markers.
        context = " ".join(t for t in self.transcriptions if not t.startswith(ERROR_PREFIX))
        prompt = build_prompt(self.base_prompt, context)
        t0 = time.perf_counter()
        try:
            raw = self.engine.transcribe(chunk, prompt)
        except Exception as exc:
            logger.error("Transcription error on %.1fs chunk", audio_s, exc_info=True)
            self.transcriptions.append(f"{ERROR_PREFIX} {exc}]")
            return
        elapsed = time.perf_counter() - t0
        text = filter_phantoms(raw)
        self.chunk_stats.append(ChunkStat(audio_s, elapsed, len(text)))
        # Log sizes and timing only — never transcript content (PHI).
        logger.info("Chunk %.1fs -> %d chars in %.2fs (RTF %.2f)",
                    audio_s, len(text), elapsed, elapsed / audio_s if audio_s else 0)
        if text:
            self.transcriptions.append(text)

    # ── Internals ────────────────────────────────────────────────────────────
    def _update_level(self, data: bytes) -> None:
        if rms_int16(data) > self.level_threshold_rms:
            self.audio_detected = True
            self._indicator_hold = INDICATOR_HOLD_READS
        elif self._indicator_hold > 0:
            self._indicator_hold -= 1
        else:
            self.audio_detected = False

    def _close_stream(self) -> None:
        """Close the stream and release its PyAudio instance (one per session)."""
        stream, self._stream = self._stream, None
        owner, self._stream_owner = self._stream_owner, None
        if stream is not None:
            for op in ("stop_stream", "close"):
                try:
                    getattr(stream, op)()
                except Exception as exc:
                    logger.warning("Stream %s failed: %s", op, exc)
        if owner is not None:
            try:
                owner.terminate()
            except Exception as exc:
                logger.warning("PyAudio terminate failed: %s", exc)

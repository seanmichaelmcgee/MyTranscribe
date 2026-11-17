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

Pause-aware mode (pause_aware=True, off by default; see pause_flow.py) changes
what the worker does with each chunk, not how audio is captured:
  * the unfinished last sentence of a chunk is not committed; its audio (at
    most CARRY_MAX_S) is decoded again at the start of the next chunk, so a
    cut in a thinking pause no longer puts a full stop mid-sentence. To keep
    every decode within the model's 30 s window the capture target shrinks to
    chunk_target_s - CARRY_MAX_S (24 s);
  * holes in the word timings that contain sound get a quick second listen,
    to recover a spoken command ("new paragraph") that the model left out;
  * a failed decode is retried once before an error marker replaces the text;
  * a chunk is skipped as silent only if no 0.3 s stretch of it is above the
    level threshold (a long pause no longer hides a few quiet words).
post_roll_s (0 by default) keeps capturing briefly after Stop, so a last word
that is still being spoken when the key is released is not cut off.

Audio format (CLAUDE.md: document chunk size/format/rate):
  capture: 16 kHz, mono, int16 (paInt16), FRAMES_PER_BUFFER = 1024 samples (64 ms)
  chunks : float32 in [-1, 1], target CHUNK_TARGET_S = 30 s, cut point chosen
           as the lowest-energy 30 ms frame within the last CUT_SEARCH_S = 5 s
  memory : 32 KB/s while buffered -> 1 h session = ~115 MB worst case
"""

import logging
import math
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
# Matched large-v3 beam-5 trials on 30 real recordings (2026-10-04): 30 s
# improved letter WER 7.2 -> 4.0%, with identical short transcripts. Stop flushes
# any shorter remainder immediately; this is not a minimum recording length.
# Longer unfinished chunks can require more compute. See the optimization report.
CHUNK_TARGET_S = 30.0
CUT_SEARCH_S = 5.0                # look this far back for a pause to cut at
CUT_FRAME_MS = 30                 # energy window for finding the pause
MAX_SESSION_S = 60 * 60           # hard cap: 1 hour per recording
LEVEL_THRESHOLD_RMS = 80          # int16 RMS; whispered speech still needs validation
INDICATOR_HOLD_READS = 10         # keep level indicator lit ~640 ms after speech
PROMPT_TAIL_CHARS = 200           # previous-chunk text fed forward as context
MAX_CONSECUTIVE_READ_ERRORS = 50  # ~ mic unplugged -> end the session cleanly
ERROR_PREFIX = "[Transcription Error:"
CARRY_MAX_S = 6.0                 # pause-aware: longest unfinished sentence handed to the next chunk
POST_ROLL_S = 0.3                 # suggested post_roll_s for hold-to-talk (the default is 0: off)
SILENCE_WINDOW_S = 0.3            # pause-aware: a chunk is silent only if every window this long is
MAX_RESCUES_PER_CHUNK = 8         # pause-aware: commands put back per chunk, at most

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


GAIN_DB_PER_STEP = 0.4            # mic gain slider 0..100: 50 = unchanged, 0 = -20 dB, 100 = +20 dB


def gain_from_slider(value) -> float:
    """Options -> Microphone gain (0..100, 50 = as the microphone sends it) as a factor."""
    try:
        v = max(0, min(100, int(value)))
    except (TypeError, ValueError, OverflowError):
        v = 50
    return 10 ** ((v - 50) * GAIN_DB_PER_STEP / 20)


def apply_gain(data: bytes, gain: float) -> bytes:
    """int16 PCM bytes times `gain`, clipped to the int16 range. Gain 1 returns the bytes untouched."""
    if gain == 1.0 or not data:
        return data
    a = np.frombuffer(data, dtype=np.int16).astype(np.float32) * gain
    return np.clip(np.rint(a), -32768, 32767).astype(np.int16).tobytes()


@dataclass(frozen=True)
class InputLevel:
    """Latest captured frame's normalized RMS and peak, before speech filtering.

    Measured after the microphone gain (Options), on exactly the audio that is
    transcribed. This immutable snapshot contains no audio and can be read by the GUI.
    """
    rms: float = 0.0
    peak: float = 0.0

    @property
    def dbfs(self) -> float:
        return 20 * math.log10(self.rms) if self.rms > 0 else -math.inf


def input_level(data: bytes) -> InputLevel:
    samples = int16_bytes_to_float32(data)
    if not samples.size:
        return InputLevel()
    return InputLevel(float(np.sqrt(np.mean(np.square(samples)))),
                      float(np.max(np.abs(samples))))


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


def chunk_has_no_speech_level(samples: np.ndarray, threshold_rms: float = LEVEL_THRESHOLD_RMS,
                              window_s: float = SILENCE_WINDOW_S, sample_rate: int = SAMPLE_RATE) -> bool:
    """
    True if no window_s stretch of a float32 chunk reaches the threshold (int16 RMS units).
    Unlike chunk_is_silent, a short phrase after a long pause is not averaged away.
    """
    win = max(1, int(window_s * sample_rate))
    if samples.size < win:
        return chunk_is_silent(samples, threshold_rms)
    usable = (samples.size // win) * win
    frames = samples[:usable].astype(np.float32).reshape(-1, win)
    loudest = float(np.sqrt(np.max(np.mean(np.square(frames), axis=1)))) * 32768.0
    return loudest < threshold_rms and chunk_is_silent(samples[usable:], threshold_rms)


def sound_seconds(samples: np.ndarray, threshold_rms: float = LEVEL_THRESHOLD_RMS,
                  window_s: float = 0.05, sample_rate: int = SAMPLE_RATE) -> float:
    """Seconds of a float32 chunk whose window_s frames reach the threshold (int16 RMS units)."""
    win = max(1, int(window_s * sample_rate))
    usable = (samples.size // win) * win
    if usable == 0:
        return 0.0
    frames = samples[:usable].astype(np.float32).reshape(-1, win)
    rms = np.sqrt(np.mean(np.square(frames), axis=1)) * 32768.0
    return float(np.count_nonzero(rms >= threshold_rms)) * window_s


def speech_level(samples: np.ndarray, threshold_rms: float = LEVEL_THRESHOLD_RMS,
                 window_s: float = 0.05, sample_rate: int = SAMPLE_RATE) -> float:
    """
    The level (int16 RMS units) above which a 50 ms frame of this chunk counts
    as speech rather than room noise: 12 dB over the chunk's own noise floor
    (its quietest tenth of frames), and never below the fixed threshold. A
    noisy room or a hissy headset then does not make every pause look like speech.
    """
    win = max(1, int(window_s * sample_rate))
    usable = (samples.size // win) * win
    if usable == 0:
        return threshold_rms
    frames = samples[:usable].astype(np.float32).reshape(-1, win)
    rms = np.sqrt(np.mean(np.square(frames), axis=1)) * 32768.0
    return max(threshold_rms, 4.0 * float(np.percentile(rms, 10)))


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
    prompt_builder : callable(context) -> prompt, optional
        Replaces the static base_prompt + context prompt (see vocab.py).
    postprocess : callable(text) -> text, optional
        Applied to each chunk after phantom filtering (see vocab_correct.py).
    stream_factory : callable returning (stream, owner_or_None)
        stream needs read(n, exception_on_overflow=False), stop_stream(), close().
        Injected by tests and the stress harness.
    """

    def __init__(self, engine, base_prompt: str = "",
                 stream_factory: Optional[Callable] = None,
                 chunk_target_s: float = CHUNK_TARGET_S,
                 cut_search_s: float = CUT_SEARCH_S,
                 max_session_s: float = MAX_SESSION_S,
                 level_threshold_rms: float = LEVEL_THRESHOLD_RMS,
                 prompt_builder: Optional[Callable[[str], str]] = None,
                 postprocess: Optional[Callable[[str], str]] = None,
                 pause_aware: bool = False,
                 carry_max_s: float = CARRY_MAX_S,
                 post_roll_s: float = 0.0) -> None:
        self.engine = engine
        self.base_prompt = base_prompt
        self.prompt_builder = prompt_builder      # context -> prompt (vocab.PromptBuilder)
        self.postprocess = postprocess            # text -> text (vocab_correct.TermCorrector)
        self._stream_factory = stream_factory or _default_stream_factory
        self.chunk_target_s = chunk_target_s
        self.cut_search_s = min(cut_search_s, chunk_target_s / 2)
        self.max_session_s = max_session_s
        self.level_threshold_rms = level_threshold_rms
        self.gain = 1.0                 # microphone gain factor (Options); 1 = unchanged
        self._carry_limit_s = max(0.0, min(carry_max_s, chunk_target_s / 2))
        self.pause_aware = False
        self.carry_max_s = 0.0
        self.post_roll_s = 0.0
        self.rescued_commands = 0       # commands put back by pause-aware decoding (diagnostics)

        self.transcriptions: List[str] = []
        self.chunk_stats: List[ChunkStat] = []
        self.audio_detected = False
        self.input_level = InputLevel()
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
        self._stop_at_samples: Optional[int] = None   # post-roll: capture ends at this sample count
        self._closing = False               # the last audio of the session has been queued
        self.set_pause_aware(pause_aware, post_roll_s)

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

    @property
    def captured_s(self) -> float:
        """Seconds of audio read from the microphone in this session."""
        return self._captured_samples / SAMPLE_RATE

    def set_pause_aware(self, pause_aware: bool, post_roll_s: float = 0.0) -> None:
        """
        Choose the classic or the pause-aware pipeline for the NEXT recording
        (ignored while one is running). Pause-aware decoding needs word timings,
        so an engine without transcribe_words() keeps the classic path.
        """
        if self._running or self.busy:
            return
        self.pause_aware = bool(pause_aware) and hasattr(self.engine, "transcribe_words")
        self.carry_max_s = self._carry_limit_s if self.pause_aware else 0.0
        self.post_roll_s = max(0.0, post_roll_s)

    def start_recording(self, mode: str = "normal") -> None:
        """Open the mic and start the capture + worker threads for a new session."""
        if self._running or self.busy:
            raise RuntimeError("previous session still active")
        self.long_mode = (mode == "long")
        self.transcriptions = []
        self.chunk_stats = []
        self.auto_stopped = False
        self.capture_error = None
        self.rescued_commands = 0
        self._stop_at_samples = None
        self._closing = False
        self._buffer = bytearray()
        self._captured_samples = 0
        self._queue = queue.Queue()
        self.input_level = InputLevel()
        self.audio_detected = False
        self._indicator_hold = 0
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
        thread = self._capture_thread
        if (self.post_roll_s > 0 and self._running and thread is not None
                and thread is not threading.current_thread() and thread.is_alive()):
            # Post-roll: let the capture thread read a little more before it stops.
            self._stop_at_samples = self._captured_samples + int(self.post_roll_s * SAMPLE_RATE)
            thread.join(timeout=self.post_roll_s + 1.0)
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
        self._closing = True             # anything still queued is the end of the recording
        self._queue.put(None)            # sentinel: worker exits after draining
        self.audio_detected = False
        self.input_level = InputLevel()
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
        # Pause-aware: leave room for the carried sentence inside the model's window.
        target_bytes = int((self.chunk_target_s - self.carry_max_s) * SAMPLE_RATE) * BYTES_PER_SAMPLE
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
            data = apply_gain(data, self.gain)   # the meter, the silence check and the model all hear this
            self._update_level(data)
            self._buffer.extend(data)
            self._captured_samples += len(data) // BYTES_PER_SAMPLE
            if self._stop_at_samples is not None and self._captured_samples >= self._stop_at_samples:
                self._running = False        # post-roll complete; stop_recording queues the rest
                break
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
        carry = None                      # pause-aware: audio of the unfinished last sentence
        while True:
            chunk = self._queue.get()
            if chunk is None:
                if carry is not None:
                    self._transcribe_pause_aware(carry, final=True)
                return
            if not self.pause_aware:
                self._transcribe_chunk(chunk)
                continue
            if carry is not None:
                chunk = np.concatenate([carry, chunk])
            with self._queue.mutex:
                final = self._closing and all(item is None for item in self._queue.queue)
            carry = self._transcribe_pause_aware(chunk, final)

    def _prompt_for_next_chunk(self) -> str:
        # Context = previous good text only; never prime Whisper with error markers.
        context = " ".join(t for t in self.transcriptions if not t.startswith(ERROR_PREFIX))
        if self.prompt_builder is not None:
            try:
                return self.prompt_builder(context)
            except Exception:
                logger.error("Prompt builder failed; using static prompt", exc_info=True)
        return build_prompt(self.base_prompt, context)

    def _transcribe_pause_aware(self, chunk: np.ndarray, final: bool) -> Optional[np.ndarray]:
        """
        Decode a chunk with word timings; commit its complete sentences (all of
        it when `final`). Returns the audio to decode again with the next chunk.
        """
        import pause_flow
        audio_s = len(chunk) / SAMPLE_RATE
        if chunk_has_no_speech_level(chunk, self.level_threshold_rms):
            logger.info("Skipping silent chunk (%.1fs)", audio_s)
            return None
        prompt = self._prompt_for_next_chunk()
        t0 = time.perf_counter()
        words = error = None
        for attempt in (1, 2):
            try:
                words = self.engine.transcribe_words(chunk, prompt)
                break
            except Exception as exc:
                logger.error("Transcription error on %.1fs chunk (attempt %d)", audio_s, attempt, exc_info=True)
                error = exc
        if words is None:
            self.transcriptions.append(f"{ERROR_PREFIX} {error}]")
            return None
        try:
            words = self._rescue_commands(chunk, words, audio_s)
        except Exception:
            logger.error("Command recovery failed; keeping the decoded text", exc_info=True)
        carry = None
        if not final:
            words, carry_from = pause_flow.split_for_carry(words, audio_s, self.carry_max_s)
            if carry_from is None:
                carry_from = pause_flow.unheard_tail(words, chunk, SAMPLE_RATE, self.carry_max_s)
            if carry_from is not None:
                carry = chunk[int(carry_from * SAMPLE_RATE):]
        self._commit(pause_flow.words_text(words), audio_s, time.perf_counter() - t0)
        return carry

    def _rescue_commands(self, chunk: np.ndarray, words: list, audio_s: float) -> list:
        """
        Listen again (a quick decode each) to the holes in the word timings
        that could hold a spoken command, and put back a command found in one.
        Most holes are pauses and cost nothing: they must contain enough sound
        to be speech and must not sit next to a command that is already there.
        """
        import pause_flow
        found = []
        level = None
        for index, a, b, start, end in pause_flow.rescue_holes(words, audio_s):
            if len(found) >= MAX_RESCUES_PER_CHUNK or pause_flow.command_near(words, index):
                continue
            if level is None:
                level = speech_level(chunk, self.level_threshold_rms)
            core = chunk[int(a * SAMPLE_RATE):int(b * SAMPLE_RATE)]
            if sound_seconds(core, level) < pause_flow.RESCUE_MIN_SOUND_S:
                continue
            lo = int(start * SAMPLE_RATE)
            heard = self.engine.transcribe_words(chunk[lo:int(end * SAMPLE_RATE)],
                                                 pause_flow.LISTEN_PROMPT, quick=True)
            hit = pause_flow.command_in_hole(heard, words, index)
            if hit is not None:
                command, c0, c1 = hit
                found.append((index, max(a, start + c0), min(b, start + c1), command))
        if found:
            self.rescued_commands += len(found)
            logger.info("Recovered %d spoken command(s) the model left out", len(found))
        return pause_flow.insert_commands(words, found)

    def _transcribe_chunk(self, chunk: np.ndarray) -> None:
        audio_s = len(chunk) / SAMPLE_RATE
        if chunk_is_silent(chunk, self.level_threshold_rms):
            logger.info("Skipping silent chunk (%.1fs)", audio_s)
            return
        prompt = self._prompt_for_next_chunk()
        t0 = time.perf_counter()
        try:
            raw = self.engine.transcribe(chunk, prompt)
        except Exception as exc:
            logger.error("Transcription error on %.1fs chunk", audio_s, exc_info=True)
            self.transcriptions.append(f"{ERROR_PREFIX} {exc}]")
            return
        self._commit(raw, audio_s, time.perf_counter() - t0)

    def _commit(self, raw: str, audio_s: float, elapsed: float) -> None:
        """Phantom filter, post-processing, stats; append the text if any is left."""
        text = filter_phantoms(raw)
        if text and self.postprocess is not None:
            try:
                text = self.postprocess(text)
            except Exception:
                logger.error("Post-processing failed; keeping raw text", exc_info=True)
        self.chunk_stats.append(ChunkStat(audio_s, elapsed, len(text)))
        # Log sizes and timing only — never transcript content (PHI).
        logger.info("Chunk %.1fs -> %d chars in %.2fs (RTF %.2f)",
                    audio_s, len(text), elapsed, elapsed / audio_s if audio_s else 0)
        if text:
            self.transcriptions.append(text)

    # ── Internals ────────────────────────────────────────────────────────────
    def _update_level(self, data: bytes) -> None:
        level = input_level(data)
        self.input_level = level
        if level.rms * 32768.0 > self.level_threshold_rms:
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

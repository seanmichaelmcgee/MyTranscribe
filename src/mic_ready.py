"""
mic_ready.py — keep the microphone open between dictations (like Dragon), with pre-roll.

Opening a microphone per recording loses the start of speech on some devices:
Bluetooth headsets deliver ~0.3 s of near-silence after the stream opens
(measured 2026-10-03), so a word spoken the moment you press Start is clipped.

ReadyMic opens the default microphone once and reads it continuously on its own
thread. Between dictations only the last PREROLL_S of audio is kept, in a small
in-memory ring buffer that is constantly overwritten (never written to disk,
never transcribed). When a recording starts, that pre-roll is handed over first,
so even a word spoken *while* pressing Start is captured. Trade-off: Windows
shows the microphone as in use while the app is open, and a Bluetooth headset
stays in call mode.

session() returns a PyAudio-like stream for ChunkedTranscriber: read() gives the
pre-roll then live audio; close() ends the session but leaves the device open.
If the device fails (unplugged), session reads raise OSError so the recording
ends cleanly with a message, and the reader keeps trying to reopen it.
"""

import collections
import logging
import queue
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("mic_ready")

FRAMES_PER_BUFFER = 1024          # 64 ms at 16 kHz, same as chunked_transcriber
PREROLL_S = 0.5
REOPEN_EVERY_S = 2.0
SESSION_READ_TIMEOUT_S = 1.0


class _Session:
    """What ChunkedTranscriber reads from during one recording."""

    def __init__(self, mic: "ReadyMic", frames):
        self._mic = mic
        self.q: "queue.Queue[bytes]" = queue.Queue()
        for f in frames:                       # pre-roll first
            self.q.put(f)
        self.closed = False

    def read(self, n, exception_on_overflow=False):
        if self.closed:
            return b""
        try:
            return self.q.get(timeout=SESSION_READ_TIMEOUT_S)
        except queue.Empty:
            raise OSError(-9999, f"microphone not delivering audio ({self._mic.error or 'no data'})")

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True
        self._mic._end_session(self)


class ReadyMic:
    def __init__(self, open_stream: Optional[Callable] = None, preroll_s: float = PREROLL_S,
                 frames_per_buffer: int = FRAMES_PER_BUFFER, sample_rate: int = 16000):
        if open_stream is None:
            from chunked_transcriber import _default_stream_factory
            open_stream = _default_stream_factory
        self._open = open_stream
        n = max(1, int(round(preroll_s * sample_rate / frames_per_buffer)))
        self._ring = collections.deque(maxlen=n)
        self._frames = frames_per_buffer
        self._lock = threading.Lock()
        self._session: Optional[_Session] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None
        self.reads = 0                        # for tests / diagnostics

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="mic-ready", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        with self._lock:
            self._ring.clear()               # drop the pre-roll on exit

    # ── Sessions ──────────────────────────────────────────────────────────────
    def session(self):
        """Start a recording: returns (stream, None) for ChunkedTranscriber's stream_factory."""
        with self._lock:
            if self._session is not None:
                self._session.closed = True
            s = _Session(self, list(self._ring))
            self._ring.clear()
            self._session = s
        return s, None

    def _end_session(self, s: _Session) -> None:
        with self._lock:
            if self._session is s:
                self._session = None

    # ── Reader thread ─────────────────────────────────────────────────────────
    def _loop(self) -> None:
        stream = owner = None
        while self._running:
            if stream is None:
                try:
                    stream, owner = self._open()
                    self.error = None
                    logger.info("Microphone open (kept ready, %.1f s pre-roll)",
                                self._ring.maxlen * self._frames / 16000)
                except Exception as exc:
                    self.error = f"cannot open microphone: {exc}"
                    logger.warning("%s; retrying in %.0f s", self.error, REOPEN_EVERY_S)
                    time.sleep(REOPEN_EVERY_S)
                    continue
            try:
                data = stream.read(self._frames, exception_on_overflow=False)
            except Exception as exc:
                self.error = f"microphone read failed: {exc}"
                logger.warning("%s; reopening", self.error)
                _close(stream, owner)
                stream = owner = None
                time.sleep(0.2)
                continue
            if not data:                       # finite test stream ended
                time.sleep(0.01)
                continue
            self.reads += 1
            with self._lock:
                if self._session is not None:
                    self._session.q.put(data)
                else:
                    self._ring.append(data)
        _close(stream, owner)


def _close(stream, owner) -> None:
    for obj, op in ((stream, "stop_stream"), (stream, "close"), (owner, "terminate")):
        if obj is not None:
            try:
                getattr(obj, op)()
            except Exception:
                pass

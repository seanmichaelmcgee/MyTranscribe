"""Test doubles for the audio stream and the speech engine."""

import threading
import time

import numpy as np

SR = 16000


def speech_like(seconds, seed=0, amplitude=3000, gaps=()):
    """
    int16 audio that is 'loud' (noise bursts) except for silent gaps.
    gaps: iterable of (start_s, end_s) to zero out.
    """
    rng = np.random.default_rng(seed)
    a = (rng.standard_normal(int(seconds * SR)) * amplitude).clip(-32767, 32767).astype(np.int16)
    for g0, g1 in gaps:
        a[int(g0 * SR):int(g1 * SR)] = 0
    return a


class ArrayStream:
    """
    PyAudio-like stream over an int16 array. read() returns b"" at the end
    (which ChunkedTranscriber treats as end-of-input). pace_s simulates the
    real 64 ms blocking read (0 = as fast as possible).
    """

    def __init__(self, samples, pace_s=0.0):
        self.data = samples.astype(np.int16).tobytes()
        self.pos = 0
        self.pace_s = pace_s
        self.stopped = False
        self.closed = False
        self.reads = 0

    def read(self, n, exception_on_overflow=False):
        if self.pace_s:
            time.sleep(self.pace_s)
        self.reads += 1
        chunk = self.data[self.pos:self.pos + n * 2]
        self.pos += len(chunk)
        return chunk

    def stop_stream(self):
        self.stopped = True

    def close(self):
        self.closed = True


class EndlessStream(ArrayStream):
    """Loops the given audio forever (until the transcriber stops reading)."""

    def read(self, n, exception_on_overflow=False):
        if self.pace_s:
            time.sleep(self.pace_s)
        self.reads += 1
        need = n * 2
        out = bytearray()
        while len(out) < need:
            take = self.data[self.pos:self.pos + need - len(out)]
            out += take
            self.pos = (self.pos + len(take)) % len(self.data)
        return bytes(out)


class FailingStream(ArrayStream):
    """Every read raises, like an unplugged USB microphone."""

    def __init__(self):
        super().__init__(np.zeros(1, dtype=np.int16))

    def read(self, n, exception_on_overflow=False):
        raise OSError(-9981, "Input overflowed / device unavailable")


class FakeOwner:
    """Stands in for the pyaudio.PyAudio instance."""

    def __init__(self):
        self.terminated = 0

    def terminate(self):
        self.terminated += 1


def factory_for(stream, owner=None):
    """stream_factory returning the same stream (and owner) every call."""
    return lambda: (stream, owner)


class FakeEngine:
    """Records every call; returns a configurable text per chunk."""

    def __init__(self, text_fn=None, delay_s=0.0, fail_on=()):
        self.calls = []          # (n_samples, prompt)
        self.text_fn = text_fn or (lambda i, audio: f"chunk{i}")
        self.delay_s = delay_s
        self.fail_on = set(fail_on)
        self.lock = threading.Lock()

    def transcribe(self, audio, prompt=None):
        with self.lock:
            i = len(self.calls)
            self.calls.append((len(audio), prompt))
        if self.delay_s:
            time.sleep(self.delay_s)
        if i in self.fail_on:
            raise RuntimeError("CUDA out of memory (fake)")
        return self.text_fn(i, audio)

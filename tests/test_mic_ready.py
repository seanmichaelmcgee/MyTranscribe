"""mic_ready: pre-roll handover, device stays open between sessions, failure and reopen."""

import time

import numpy as np

from conftest import wait_for
from mic_ready import ReadyMic


class NumberedStream:
    """Each read returns a 1024-sample frame filled with an increasing frame number."""

    def __init__(self, fail_after=None):
        self.n = 0
        self.fail_after = fail_after
        self.closed = False

    def read(self, n, exception_on_overflow=False):
        time.sleep(0.004)
        if self.fail_after is not None and self.n >= self.fail_after:
            raise OSError(-9988, "Stream closed (unplugged)")
        self.n += 1
        return np.full(n, self.n % 30000, dtype=np.int16).tobytes()

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


def frame_id(b):
    return int(np.frombuffer(b, np.int16)[0])


def test_preroll_is_handed_over_then_live_audio_follows():
    streams = []
    mic = ReadyMic(open_stream=lambda: (streams.append(NumberedStream()) or streams[-1], None), preroll_s=0.3)
    mic.start()
    try:
        assert wait_for(lambda: mic.reads > 20, timeout=3)
        s, owner = mic.session()
        first = [frame_id(s.read(1024)) for _ in range(8)]
        ring = mic._ring.maxlen
        assert len(first) == 8 and first == sorted(first)            # in order, no gaps
        assert first[1] - first[0] == 1
        assert ring == 5                                               # 0.3 s of 64 ms frames
        # The first frame handed over is from *before* the session started (pre-roll).
        assert first[0] <= mic.reads - 3
        s.close()
        assert not streams[0].closed and len(streams) == 1            # device stays open
        s2, _ = mic.session()
        assert frame_id(s2.read(1024)) > first[-1]
        s2.close()
    finally:
        mic.stop()
    assert streams[0].closed and len(mic._ring) == 0                  # closed and pre-roll dropped on exit


def test_unplug_raises_in_session_and_device_reopens():
    streams = []

    def open_stream():
        streams.append(NumberedStream(fail_after=15 if not streams else None))
        return streams[-1], None
    mic = ReadyMic(open_stream=open_stream, preroll_s=0.2)
    mic.start()
    try:
        assert wait_for(lambda: len(streams) == 2, timeout=5)          # failed once, reopened
        assert wait_for(lambda: mic.reads > 20, timeout=3)
        s, _ = mic.session()
        assert s.read(1024)                                            # audio again after reopen
        s.close()
    finally:
        mic.stop()


def test_session_read_times_out_when_no_device(monkeypatch):
    import mic_ready
    monkeypatch.setattr(mic_ready, "SESSION_READ_TIMEOUT_S", 0.05)
    monkeypatch.setattr(mic_ready, "REOPEN_EVERY_S", 0.05)

    def broken():
        raise OSError(-9996, "Invalid input device")
    mic = ReadyMic(open_stream=broken)
    mic.start()
    try:
        s, _ = mic.session()
        try:
            s.read(1024)
            raised = False
        except OSError as exc:
            raised = "not delivering" in str(exc)
        assert raised
    finally:
        mic.stop()

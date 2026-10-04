"""Chime resource lifetime without using an audio device."""
import threading
import wave

import pytest

import sound_utils


@pytest.fixture
def player(tmp_path, monkeypatch):
    path = tmp_path / "chime.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x01\x00" * 16)
    monkeypatch.setattr(sound_utils, "generate_start_chime_file", lambda: str(path))
    monkeypatch.setattr(sound_utils, "generate_end_chime_file", lambda: str(path))
    started, release = threading.Event(), threading.Event()
    events = []

    class Stream:
        def write(self, data):
            events.append("write")
            started.set()
            assert release.wait(3)
        def stop_stream(self):
            events.append("stop")
        def close(self):
            events.append("close")

    class PA:
        def get_format_from_width(self, width):
            return width
        def open(self, **kwargs):
            events.append("open")
            return Stream()
        def terminate(self):
            assert "close" in events or "open" not in events
            events.append("terminate")

    monkeypatch.setattr(sound_utils.pyaudio, "PyAudio", PA)
    return sound_utils.ChimePlayer(), started, release, events


def test_cleanup_waits_for_playback_to_close_its_stream(player):
    chime, started, release, events = player
    worker = threading.Thread(target=chime._play_sound_thread, args=(chime.start_chime_path,))
    worker.start()
    assert started.wait(2)
    shutdown = threading.Thread(target=chime.cleanup)
    shutdown.start()
    shutdown.join(0.05)
    assert shutdown.is_alive() and "terminate" not in events
    release.set()
    worker.join(2)
    shutdown.join(2)
    assert not worker.is_alive() and not shutdown.is_alive()
    assert events == ["open", "write", "stop", "close", "terminate"]
    assert chime.p is None


def test_playback_requested_after_cleanup_cannot_reopen_device(player):
    chime, _, _, events = player
    chime.cleanup()
    chime._play_sound_thread(chime.start_chime_path)
    chime.cleanup()
    assert events == ["terminate"]


def test_concurrent_chime_does_not_queue_stale_playback(player):
    chime, started, release, events = player
    worker = threading.Thread(target=chime._play_sound_thread, args=(chime.start_chime_path,))
    worker.start()
    assert started.wait(2)
    chime._play_sound_thread(chime.end_chime_path)
    release.set()
    worker.join(2)
    chime.cleanup()
    assert events.count("open") == 1


def test_failed_output_still_closes_stream_before_termination(player):
    chime, _, _, events = player
    original_open = chime.p.open
    def broken_open(**kwargs):
        stream = original_open(**kwargs)
        def fail(data):
            raise OSError("simulated output failure")
        stream.write = fail
        return stream
    chime.p.open = broken_open
    chime._play_sound_thread(chime.start_chime_path)
    chime.cleanup()
    assert events == ["open", "stop", "close", "terminate"]

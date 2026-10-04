"""chunked_transcriber: pure helpers + threaded pipeline with fake stream/engine."""

import logging
import tempfile
import threading
import time

import numpy as np
import pytest

import chunked_transcriber as ct
from chunked_transcriber import (
    ChunkedTranscriber, build_prompt, chunk_is_silent, filter_phantoms,
    find_cut_index, int16_bytes_to_float32, rms_int16,
)
from conftest import wait_for
from fakes import (
    SR, ArrayStream, EndlessStream, FailingStream, FakeEngine, FakeOwner,
    factory_for, speech_like,
)


# ── Pure helpers ────────────────────────────────────────────────────────────
def test_int16_to_float32_scaling():
    pcm = np.array([0, 16384, -32768, 32767], dtype=np.int16).tobytes()
    out = int16_bytes_to_float32(pcm)
    assert out.dtype == np.float32
    np.testing.assert_allclose(out, [0, 0.5, -1.0, 32767 / 32768])


def test_rms():
    assert rms_int16(b"") == 0.0
    assert rms_int16(np.full(100, 300, dtype=np.int16).tobytes()) == pytest.approx(300)


def test_input_level_matches_inference_scaling_without_changing_pcm():
    pcm = np.array([0, 16384, -32768, 32767], dtype=np.int16).tobytes()
    before = pcm
    samples = int16_bytes_to_float32(pcm)
    level = ct.input_level(pcm)
    assert level.rms == pytest.approx(np.sqrt(np.mean(samples ** 2)))
    assert level.peak == 1.0  # negative int16 limit must not overflow abs()
    assert level.dbfs == pytest.approx(20 * np.log10(level.rms))
    assert pcm == before
    assert ct.input_level(b"") == ct.InputLevel()
    assert ct.input_level(bytes(2048)).dbfs == -np.inf


def test_default_30_second_window_flushes_short_recording_on_stop():
    audio = speech_like(2)
    received = []
    engine = FakeEngine(text_fn=lambda i, a: received.append(a.copy()) or "Short snippet.")
    t = ChunkedTranscriber(engine, stream_factory=factory_for(ArrayStream(audio)))
    assert t.chunk_target_s == 30.0
    t.start_recording()
    assert wait_for(lambda: not t.recording, timeout=2)
    assert engine.calls == []  # the short remainder has not filled the window
    assert t.input_level.peak > 0
    started = time.perf_counter()
    t.stop_recording()
    assert t.wait_until_idle(timeout=2)
    assert time.perf_counter() - started < 2
    assert t.text == "Short snippet."
    np.testing.assert_array_equal(received[0], audio.astype(np.float32) / 32768)
    assert t.input_level == ct.InputLevel()


def test_find_cut_lands_in_the_pause():
    a = speech_like(30, gaps=[(27.0, 27.4)]).astype(np.float32)
    cut = find_cut_index(a, search_s=5)
    assert 27.0 * SR <= cut <= 27.4 * SR


def test_find_cut_ignores_pauses_outside_search_window():
    a = speech_like(30, gaps=[(10.0, 11.0)]).astype(np.float32)
    assert find_cut_index(a, search_s=5) >= 25 * SR


def test_find_cut_short_buffers():
    assert find_cut_index(np.zeros(10, dtype=np.float32)) == 10
    assert find_cut_index(np.zeros(0, dtype=np.float32)) == 0


def test_find_cut_prefers_latest_equal_silence():
    a = np.zeros(30 * SR, dtype=np.float32)       # all silent: cut near the end
    assert find_cut_index(a, search_s=5) > 29.9 * SR


def test_chunk_is_silent():
    assert chunk_is_silent(np.zeros(SR, dtype=np.float32))
    assert chunk_is_silent(np.array([], dtype=np.float32))
    loud = int16_bytes_to_float32(speech_like(1).tobytes())
    assert not chunk_is_silent(loud)


@pytest.mark.parametrize("text", ["Thank you.", " thanks for watching!", "You", "Bye-bye.",
                                  "Subtitles by the Amara.org community"])
def test_phantom_chunks_dropped(text):
    assert filter_phantoms(text) == ""


@pytest.mark.parametrize("text", [
    "Thank you for seeing Mrs. Jones, a 64-year-old woman.",
    "Thank you, Dr. Patel.",
    "So she was started on apixaban.",
])
def test_real_dictation_kept(text):
    # transcriber_v12 would have stripped a leading "Thank you" here.
    assert filter_phantoms(text) == text


def test_trailing_youtube_phrase_trimmed():
    assert filter_phantoms("Follow up in six weeks. Thanks for watching!") == "Follow up in six weeks"


def test_build_prompt():
    assert build_prompt("Vocab.", "") == "Vocab."
    assert build_prompt("", "short text") == "short text"
    prev = "alpha " * 100 + "the patient tolerated metformin well"
    p = build_prompt("Vocab.", prev, tail_chars=60)
    assert p.startswith("Vocab. ") and p.endswith("tolerated metformin well")
    assert not p.split("Vocab. ")[1].startswith("lpha")   # not mid-word


# ── Pipeline ────────────────────────────────────────────────────────────────
def run_session(audio, engine=None, chunk_target_s=10.0, **kw):
    """Feed a finite array through a transcriber; wait for capture + transcription."""
    engine = engine or FakeEngine()
    owner = FakeOwner()
    stream = ArrayStream(audio)
    t = ChunkedTranscriber(engine, "Vocab.", stream_factory=factory_for(stream, owner),
                           chunk_target_s=chunk_target_s, **kw)
    t.start_recording()
    assert wait_for(lambda: not t.recording, timeout=10)
    t.stop_recording()
    assert t.wait_until_idle(timeout=10)
    return t, engine, stream, owner


def test_all_audio_transcribed_once_in_order():
    audio = speech_like(95, gaps=[(8.5, 8.8), (19, 19.3), (29.2, 29.5)])
    t, engine, stream, owner = run_session(audio)
    lengths = [n for n, _ in engine.calls]
    assert sum(lengths) == len(audio)                 # no audio lost or duplicated
    assert len(lengths) >= 9
    assert all(n <= 10 * SR + 1024 for n in lengths)  # chunks near target
    assert t.text == " ".join(f"chunk{i}" for i in range(len(lengths)))
    assert stream.closed and stream.stopped and owner.terminated == 1
    assert t.auto_stopped                             # finite stream ended capture


def test_prompt_carries_previous_text():
    t, engine, *_ = run_session(speech_like(25))
    assert engine.calls[0][1] == "Vocab."
    assert engine.calls[1][1] == "Vocab. chunk0"


def test_silent_session_never_calls_engine():
    t, engine, *_ = run_session(np.zeros(20 * SR, dtype=np.int16))
    assert engine.calls == [] and t.text == ""


def test_silent_middle_chunk_skipped():
    audio = speech_like(30, gaps=[(10, 20)])
    t, engine, *_ = run_session(audio)
    assert sum(n for n, _ in engine.calls) < len(audio)
    assert len(t.transcriptions) == len(engine.calls)


def test_engine_error_is_reported_and_later_chunks_continue():
    t, engine, *_ = run_session(speech_like(35), engine=FakeEngine(fail_on={1}))
    assert len(engine.calls) >= 3
    assert len(t.transcriptions) == len(engine.calls)
    assert t.transcriptions[1].startswith("[Transcription Error:")
    assert t.transcriptions[2] == "chunk2"
    # The error marker must not leak into the next chunk's Whisper prompt.
    assert engine.calls[2][1] == "Vocab. chunk0"


def test_phantom_outputs_filtered_in_pipeline():
    eng = FakeEngine(text_fn=lambda i, a: "Thank you." if i == 0 else "Plan: echo.")
    t, *_ = run_session(speech_like(15), engine=eng)
    assert t.text == "Plan: echo."


def test_stop_returns_fast_while_engine_is_slow():
    engine = FakeEngine(delay_s=1.0)
    stream = EndlessStream(speech_like(5), pace_s=0.002)
    t = ChunkedTranscriber(engine, stream_factory=factory_for(stream), chunk_target_s=2.0)
    t.start_recording()
    assert wait_for(lambda: len(engine.calls) >= 1, timeout=5)
    t0 = time.perf_counter()
    t.stop_recording()
    assert time.perf_counter() - t0 < 0.5
    assert t.busy
    with pytest.raises(RuntimeError):
        t.start_recording()                        # previous session still draining
    assert t.wait_until_idle(timeout=30)
    assert not t.busy and t.text.startswith("chunk0")


def test_session_cap_auto_stops():
    stream = EndlessStream(speech_like(3))
    t = ChunkedTranscriber(FakeEngine(), stream_factory=factory_for(stream),
                           chunk_target_s=2.0, max_session_s=5.0)
    t.start_recording()
    assert wait_for(lambda: not t.recording, timeout=10)
    assert t.auto_stopped and t.capture_error is None
    t.stop_recording()
    assert t.wait_until_idle(timeout=10)
    total = sum(s.audio_s for s in t.chunk_stats)
    assert 5.0 <= total < 5.2


def test_microphone_failure_ends_session_cleanly(monkeypatch):
    monkeypatch.setattr(ct.time, "sleep", lambda s: None)
    t = ChunkedTranscriber(FakeEngine(), stream_factory=factory_for(FailingStream()))
    t.start_recording()
    assert wait_for(lambda: not t.recording, timeout=5)
    assert t.auto_stopped and "microphone read failed" in t.capture_error
    t.stop_recording()
    assert t.wait_until_idle(timeout=5) and t.text == ""


def test_double_stop_is_harmless():
    t, *_ = run_session(speech_like(3))
    t.stop_recording()
    t.cleanup()


def test_level_indicator():
    t = ChunkedTranscriber(FakeEngine())
    t._update_level(speech_like(0.064).tobytes())
    assert t.audio_detected
    quiet = np.zeros(1024, dtype=np.int16).tobytes()
    for _ in range(ct.INDICATOR_HOLD_READS):
        t._update_level(quiet)
    assert t.audio_detected                      # held briefly after speech
    t._update_level(quiet)
    assert not t.audio_detected


def test_no_thread_or_pyaudio_leak_over_many_sessions():
    baseline = threading.active_count()
    owner = FakeOwner()
    engine = FakeEngine()
    for i in range(100):
        stream = ArrayStream(speech_like(0.5, seed=i))
        t = ChunkedTranscriber(engine, stream_factory=factory_for(stream, owner))
        t.start_recording()
        t.stop_recording()
        assert t.wait_until_idle(timeout=5)
    assert owner.terminated == 100
    assert wait_for(lambda: threading.active_count() <= baseline, timeout=5)


def test_no_temp_files_written(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("audio must not be written to disk")
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", boom)
    monkeypatch.setattr(tempfile, "mkstemp", boom)
    t, engine, *_ = run_session(speech_like(12))
    assert engine.calls


def test_transcript_text_never_logged(caplog):
    secret = "Mrs. Zebediah Quartermaine DOB 1961"
    caplog.set_level(logging.DEBUG)
    t, *_ = run_session(speech_like(12), engine=FakeEngine(text_fn=lambda i, a: secret))
    assert secret in t.text
    assert "Zebediah" not in caplog.text

"""ChunkedTranscriber pause-aware mode: carry-over, command recovery, retry, post-roll (fakes only)."""

import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

import pause_flow
import voice_commands
from chunked_transcriber import ChunkedTranscriber, chunk_has_no_speech_level, chunk_is_silent
from conftest import wait_for
from fakes import SR, ArrayStream, EndlessStream, FakeEngine, factory_for, speech_like
from fw_engine import FasterWhisperEngine
from hw_profile import EngineConfig


class WordEngine:
    """
    Engine with word timings. script: one entry per chunk decode, each a list
    of (text, start_s, end_s) or an Exception to raise; past its end a single
    word "more.". holes: the same for second listens (the quick calls); past
    its end, nothing heard.
    """

    def __init__(self, script=(), holes=()):
        self.script = list(script)
        self.holes = list(holes)
        self.calls = []                  # chunk decodes: (n_samples, prompt)
        self.hole_calls = []             # second listens: n_samples
        self.plain_calls = 0
        self.lock = threading.Lock()

    def transcribe(self, audio, prompt=None):
        self.plain_calls += 1
        return "classic"

    def transcribe_words(self, audio, prompt=None, quick=False):
        with self.lock:
            if quick:
                assert prompt == pause_flow.LISTEN_PROMPT
                i = len(self.hole_calls)
                self.hole_calls.append(len(audio))
                item = self.holes[i] if i < len(self.holes) else []
            else:
                i = len(self.calls)
                self.calls.append((len(audio), prompt))
                item = self.script[i] if i < len(self.script) else [("more.", 0.1, 0.5)]
        if isinstance(item, Exception):
            raise item
        return [(" " + w, s, e) for w, s, e in item]


def run(audio, engine, chunk_target_s=10.0, carry_max_s=4.0, **kw):
    t = ChunkedTranscriber(engine, "Vocab.", stream_factory=factory_for(ArrayStream(audio)),
                           chunk_target_s=chunk_target_s, pause_aware=True, carry_max_s=carry_max_s, **kw)
    t.start_recording()
    assert wait_for(lambda: not t.recording, timeout=10)
    t.stop_recording()
    assert t.wait_until_idle(timeout=10)
    return t


# 5 s of "speech" with quiet edges, so the chunk has a noise floor to compare a hole against.
QUIET_EDGES = speech_like(5, gaps=[(0.0, 0.3), (4.6, 5.0)])


def test_speech_level_is_relative_to_the_noise_floor():
    from chunked_transcriber import sound_seconds, speech_level
    hiss = speech_like(4, amplitude=200).astype(np.float32) / 32768.0       # noisy room, no speech
    voice = speech_like(1, amplitude=4000, seed=1).astype(np.float32) / 32768.0
    chunk = np.concatenate([hiss[:2 * SR], voice, hiss[2 * SR:]])
    assert sound_seconds(chunk) == pytest.approx(5.0, abs=0.06)             # fixed threshold: all "sound"
    level = speech_level(chunk)
    assert sound_seconds(chunk, level) == pytest.approx(1.0, abs=0.06)      # relative: only the voice
    assert speech_level(np.zeros(SR, dtype=np.float32)) == 80               # never below the fixed one


def test_off_by_default_and_classic_path_untouched():
    engine = WordEngine()
    t = ChunkedTranscriber(engine, "Vocab.", stream_factory=factory_for(ArrayStream(speech_like(3))))
    assert not t.pause_aware and t.post_roll_s == 0 and t.carry_max_s == 0
    t.start_recording()
    assert wait_for(lambda: not t.recording)
    t.stop_recording()
    assert t.wait_until_idle(timeout=10)
    assert engine.plain_calls == 1 and engine.calls == [] and t.text == "classic"


def test_engine_without_word_timings_stays_classic():
    t = ChunkedTranscriber(FakeEngine(), pause_aware=True, post_roll_s=0.3)
    assert not t.pause_aware and t.carry_max_s == 0
    assert t.post_roll_s == 0.3                       # post-roll does not need word timings


def test_unfinished_sentence_is_decoded_again_with_its_ending():
    # First chunk (6 s target): cut fell after "daily"; Whisper wrote "daily." there.
    first = [("Atenolol", 0.2, 0.8), ("stopped.", 0.9, 1.6), ("Lisinopril", 3.0, 3.8), ("daily.", 4.0, 4.6)]
    second = [("Lisinopril", 0.3, 1.0), ("daily", 1.2, 1.8), ("remains", 4.5, 5.0), ("unchanged.", 5.1, 5.8)]
    engine = WordEngine([first, second])
    audio = speech_like(11, gaps=[(5.7, 5.9)])        # the capture cut lands in this gap
    t = run(audio, engine)                            # capture target 10 - 4 = 6 s
    assert t.transcriptions == ["Atenolol stopped.", "Lisinopril daily remains unchanged."]
    (n1, p1), (n2, p2) = engine.calls
    carried = n1 - int(2.3 * SR)                      # audio from the middle of the 1.6-3.0 s pause
    assert n2 == pytest.approx(len(audio) - n1 + carried, abs=2)
    assert n2 <= 10 * SR + 1024                       # still one model window
    assert p2 == "Vocab. Atenolol stopped."           # context is committed text only


def test_last_chunk_commits_everything():
    engine = WordEngine([[("Follow", 0.2, 0.5), ("up.", 0.6, 1.0), ("Repeat", 1.6, 2.0), ("labs", 2.1, 2.5)]])
    t = run(speech_like(3), engine)
    assert t.text == "Follow up. Repeat labs" and len(engine.calls) == 1


def test_carry_left_at_stop_is_still_transcribed():
    # Capture ends exactly on a chunk boundary: nothing is queued after the cut chunk.
    first = [("Stable.", 0.2, 0.8), ("Continue", 3.0, 3.6)]
    engine = WordEngine([first, [("Continue", 0.2, 0.8), ("metformin.", 0.9, 1.5)]])
    t = ChunkedTranscriber(engine, "Vocab.", stream_factory=factory_for(ArrayStream(speech_like(6))),
                           chunk_target_s=10.0, pause_aware=True, carry_max_s=4.0)
    t.start_recording()
    assert wait_for(lambda: len(engine.calls) == 1 or not t.recording, timeout=10)
    assert wait_for(lambda: not t.recording, timeout=10)
    t.stop_recording()
    assert t.wait_until_idle(timeout=10)
    assert t.text.startswith("Stable.") and t.text.endswith("metformin.")
    assert "Continue" in t.text


def test_dropped_command_is_put_back_and_converted():
    first = [("normal.", 0.3, 1.0), ("Ibuprofen", 3.0, 3.8), ("daily.", 3.9, 4.5)]
    hole = [("New", 0.4, 0.6), ("paragraph.", 0.6, 1.2)]
    engine = WordEngine([first], holes=[hole])
    t = run(QUIET_EDGES, engine)
    assert t.text == "normal. New paragraph. Ibuprofen daily."
    assert voice_commands.apply(t.text) == "normal.\n\nIbuprofen daily."
    assert t.rescued_commands == 1
    assert len(engine.hole_calls) == 1                # one quick second listen,
    assert engine.hole_calls[0] < 4 * SR              # to the hole only, not the chunk


def test_engine_that_declines_second_listens_gets_none():
    # On the processor a second listen is a whole model pass (2-2.5 s on laptop cores) and
    # rescued nothing on the owner's recordings: the engine says no and the text is the first pass.
    first = [("normal.", 0.3, 1.0), ("Ibuprofen", 3.0, 3.8), ("daily.", 3.9, 4.5)]
    engine = WordEngine([first], holes=[[("New", 0.4, 0.6), ("paragraph.", 0.6, 1.2)]])
    engine.second_listen = False
    t = run(QUIET_EDGES, engine)
    assert engine.hole_calls == [] and t.rescued_commands == 0
    assert t.text == "normal. Ibuprofen daily."


@pytest.mark.parametrize("device, listens", [("cpu", False), ("cuda", True)])
def test_second_listens_only_on_a_graphics_card(device, listens):
    eng = FasterWhisperEngine(EngineConfig("small.en", device, "int8", 4, "test"),
                              model_factory=lambda *a, **k: SimpleNamespace())
    assert eng.second_listen is listens


def test_graphics_card_that_fails_to_load_falls_back_without_second_listens():
    def factory(model, device, compute_type, cpu_threads):
        if device == "cuda":
            raise RuntimeError("cublas64_12.dll not found")
        return SimpleNamespace()
    eng = FasterWhisperEngine(EngineConfig("large-v3", "cuda", "int8_float32", 2, "test"), model_factory=factory)
    assert eng.config.device == "cpu" and eng.second_listen is False


def test_hole_with_other_speech_changes_nothing():
    first = [("normal.", 0.3, 1.0), ("Ibuprofen", 3.0, 3.8), ("daily.", 3.9, 4.5)]
    engine = WordEngine([first], holes=[[("Thank", 0.4, 0.6), ("you.", 0.6, 0.9)]])
    t = run(QUIET_EDGES, engine)
    assert t.text == "normal. Ibuprofen daily." and t.rescued_commands == 0
    assert len(engine.hole_calls) == 1


def test_silent_holes_cost_no_extra_decode():
    audio = speech_like(5, gaps=[(1.0, 3.0)])
    engine = WordEngine([[("normal.", 0.3, 1.05), ("Ibuprofen", 2.95, 3.9), ("daily.", 4.0, 4.9)]])
    t = run(audio, engine)
    assert engine.hole_calls == [] and t.text == "normal. Ibuprofen daily."


def test_hole_next_to_a_command_already_in_the_text_costs_no_extra_decode():
    first = [("normal.", 0.3, 1.0), ("New", 1.1, 1.2), ("paragraph.", 1.2, 1.3), ("Ibuprofen", 3.0, 3.8)]
    engine = WordEngine([first])
    t = run(speech_like(4), engine)
    assert engine.hole_calls == [] and t.text == "normal. New paragraph. Ibuprofen"


def test_sound_seconds():
    from chunked_transcriber import sound_seconds
    audio = speech_like(3, gaps=[(0.5, 2.5)]).astype(np.float32) / 32768.0
    assert sound_seconds(audio) == pytest.approx(1.0, abs=0.06)
    assert sound_seconds(np.zeros(SR, dtype=np.float32)) == 0
    assert sound_seconds(np.zeros(10, dtype=np.float32)) == 0


def test_failed_recovery_keeps_the_decoded_text():
    first = [("normal.", 0.3, 1.0), ("Ibuprofen", 3.0, 3.8), ("daily.", 3.9, 4.5)]
    t = run(speech_like(5), WordEngine([first], holes=[RuntimeError("CUDA out of memory (fake)")]))
    assert t.text == "normal. Ibuprofen daily."


def test_decode_error_is_retried_once():
    ok = [("Plan", 0.1, 0.4), ("unchanged.", 0.5, 1.0)]
    t = run(speech_like(1.2), WordEngine([RuntimeError("CUDA out of memory (fake)"), ok]))
    assert t.text == "Plan unchanged."


def test_two_failures_leave_an_error_marker_and_later_audio_continues():
    boom = RuntimeError("CUDA out of memory (fake)")
    engine = WordEngine([boom, boom, [("Later", 0.1, 0.4), ("text.", 0.5, 0.9)]])
    t = run(speech_like(8), engine)
    assert t.transcriptions[0].startswith("[Transcription Error:")
    assert t.transcriptions[1] == "Later text."
    assert engine.calls[2][1] == "Vocab."             # the marker never primes the model


def test_quiet_words_after_a_long_pause_are_not_skipped_as_silence():
    chunk = np.zeros(25 * SR, dtype=np.float32)
    chunk[23 * SR:24 * SR] = speech_like(1, amplitude=300).astype(np.float32) / 32768.0
    assert chunk_is_silent(chunk)                     # classic: averaged away
    assert not chunk_has_no_speech_level(chunk)
    assert chunk_has_no_speech_level(np.zeros(25 * SR, dtype=np.float32))
    assert chunk_has_no_speech_level(np.zeros(100, dtype=np.float32))


def _stop_after(t, seconds):
    time.sleep(seconds)
    t0 = time.perf_counter()
    t.stop_recording()
    return time.perf_counter() - t0


def test_post_roll_keeps_listening_after_stop():
    stream = EndlessStream(speech_like(2), pace_s=0.064)          # real-time microphone
    t = ChunkedTranscriber(FakeEngine(), stream_factory=factory_for(stream), post_roll_s=0.3)
    t.start_recording()
    assert wait_for(lambda: t.captured_s > 0.2)
    at_stop = t.captured_s
    took = _stop_after(t, 0)
    assert 0.3 <= t.captured_s - at_stop < 0.6
    assert took < 1.0 and not t.recording
    assert t.wait_until_idle(timeout=10)
    assert t.chunk_stats[0].audio_s == pytest.approx(t.captured_s)   # the extra audio was transcribed


def test_no_post_roll_by_default():
    stream = EndlessStream(speech_like(2), pace_s=0.064)
    t = ChunkedTranscriber(FakeEngine(), stream_factory=factory_for(stream))
    t.start_recording()
    assert wait_for(lambda: t.captured_s > 0.2)
    at_stop = t.captured_s
    _stop_after(t, 0)
    assert t.captured_s - at_stop <= 0.13
    assert t.wait_until_idle(timeout=10)


def test_post_roll_does_not_hang_on_a_dead_microphone():
    class Stalled(ArrayStream):
        def read(self, n, exception_on_overflow=False):
            time.sleep(0.05)
            raise OSError(-9999, "no data")

    t = ChunkedTranscriber(FakeEngine(), stream_factory=factory_for(Stalled(np.zeros(1, np.int16))),
                           post_roll_s=0.3)
    t.start_recording()
    took = _stop_after(t, 0.1)
    assert took < 4.0
    assert t.wait_until_idle(timeout=10)


def test_mode_cannot_change_mid_recording():
    stream = EndlessStream(speech_like(2), pace_s=0.002)
    t = ChunkedTranscriber(WordEngine(), "Vocab.", stream_factory=factory_for(stream))
    t.start_recording()
    t.set_pause_aware(True, 0.3)
    assert not t.pause_aware
    t.stop_recording()
    assert t.wait_until_idle(timeout=10)
    t.set_pause_aware(True, 0.3)
    assert t.pause_aware and t.post_roll_s == 0.3 and t.carry_max_s > 0


# ── fw_engine.transcribe_words: which decoded segments count ─────────────────
def _segment(seek, *words):
    return SimpleNamespace(seek=seek, text=" ".join(w for w, _s, _e in words),
                           words=[SimpleNamespace(word=" " + w, start=s, end=e) for w, s, e in words])


class SegmentModel:
    def __init__(self, segments, heard_s):
        self.segments, self.heard_s, self.kwargs = segments, heard_s, None

    def transcribe(self, audio, **kw):
        self.kwargs = kw
        return iter(self.segments), SimpleNamespace(duration_after_vad=self.heard_s)


def _engine(segments, heard_s):
    eng = FasterWhisperEngine(EngineConfig("m", "cpu", "int8", 1, "test"),
                              model_factory=lambda *a, **k: SegmentModel(segments, heard_s))
    return eng


def test_leftover_tail_decode_is_dropped():
    # faster-whisper decodes again from the last word's end: 0.4 s of nothing -> "Thank you."
    # (4 s of audio, 2.2 s of it trailing silence that VAD removed: only 1.8 s was heard.)
    eng = _engine([_segment(0, ("eGFR", 0.2, 0.8), ("58.", 0.9, 1.4)),
                   _segment(140, ("Thank", 1.5, 1.6), ("you.", 1.6, 1.8))], heard_s=1.8)
    out = eng.transcribe_words(np.zeros(4 * SR, dtype=np.float32), "Vocab.")
    assert [w.strip() for w, _s, _e in out] == ["eGFR", "58."]
    assert eng.model.kwargs["word_timestamps"] is True and eng.model.kwargs["without_timestamps"] is True
    assert eng.model.kwargs["beam_size"] == eng.beam_size > 1


def test_search_settings_depend_on_the_device(monkeypatch):
    import fw_engine
    from hw_profile import EngineConfig
    monkeypatch.delenv("MYTRANSCRIBE_BEAM_SIZE", raising=False)
    make = lambda device: fw_engine.FasterWhisperEngine(EngineConfig("m", device, "int8", 4, "test"),
                                                        model_factory=lambda *a, **k: object())
    cpu, gpu = make("cpu"), make("cuda")
    assert (cpu.beam_size, cpu.patience) == (fw_engine.CPU_BEAM_SIZE, fw_engine.CPU_PATIENCE) == (3, 1.0)
    assert (gpu.beam_size, gpu.patience) == (fw_engine.DEFAULT_BEAM_SIZE, fw_engine.DEFAULT_PATIENCE) == (5, 2.0)


def test_tail_decode_is_not_even_requested_when_nothing_is_left():
    asked = []

    def segments():
        yield _segment(0, ("eGFR", 0.2, 0.8), ("58.", 0.9, 1.4))
        asked.append("second window")
        yield _segment(140, ("Thank", 1.5, 1.6), ("you.", 1.6, 1.8))

    eng = _engine([], heard_s=1.8)
    eng.model.segments = segments()
    assert len(eng.transcribe_words(np.zeros(2 * SR, dtype=np.float32), "Vocab.")) == 2
    assert asked == []


def test_quick_listen_is_greedy():
    eng = _engine([], heard_s=0)
    eng.transcribe_words(np.zeros(SR, dtype=np.float32), None, quick=True)
    assert eng.model.kwargs["beam_size"] == 1 and eng.model.kwargs["patience"] == 1.0


def _speech(seconds, spans):
    """Silence with noise where speech is, spans = [(start_s, end_s)]."""
    audio = np.zeros(int(seconds * SR), dtype=np.float32)
    rng = np.random.default_rng(0)
    for a, b in spans:
        audio[int(a * SR):int(b * SR)] = (rng.standard_normal(int((b - a) * SR)) * 0.05).astype(np.float32)
    return audio


def test_real_audio_left_after_an_early_stop_is_kept():
    eng = _engine([_segment(0, ("Plan.", 0.2, 0.8)),
                   _segment(100, ("Repeat", 1.5, 2.0), ("labs.", 2.1, 2.9))], heard_s=6.0)
    assert len(eng.transcribe_words(_speech(6, [(0.2, 0.8), (1.5, 2.9)]))) == 3


def test_silence_after_the_last_word_is_not_decoded():
    # A 25 s piece that ends in 3 s of silence (the speaker stopped): asking for another window
    # costs a whole decode, 5 s on a laptop processor, for nothing.
    asked = []

    def segments():
        yield _segment(0, ("Plan", 0.2, 10.0), ("follows.", 10.1, 22.0))
        asked.append("second window")
        yield _segment(2200, ("Thank", 22.5, 22.8), ("you.", 22.8, 23.0))

    eng = _engine([], heard_s=22.4)
    eng.model.segments = segments()
    out = eng.transcribe_words(_speech(25, [(0.2, 22.0)]))
    assert [w.strip() for w, _s, _e in out] == ["Plan", "follows."] and asked == []


def test_next_full_window_is_kept():
    eng = _engine([_segment(0, ("One.", 0.2, 29.9)), _segment(2995, ("Two.", 30.0, 30.5))], heard_s=30.6)
    assert len(eng.transcribe_words(np.zeros(31 * SR, dtype=np.float32))) == 2


def test_decode_overrides_reach_the_model_and_default_is_unchanged():
    eng = _engine([], heard_s=0)
    eng.transcribe(np.zeros(SR, dtype=np.float32), "Vocab.")
    assert eng.model.kwargs["vad_parameters"] == {"min_silence_duration_ms": 700, "speech_pad_ms": 300}
    eng.decode_overrides = {"vad_filter": False}
    eng.transcribe(np.zeros(SR, dtype=np.float32), "Vocab.")
    assert eng.model.kwargs["vad_filter"] is False

"""onnx_engine: the parts that need no model or onnxruntime."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from medasr_engine import spoken_markers  # noqa: E402
from onnx_engine import OnnxAsrEngine, words_from_tokens  # noqa: E402


class _Timed:
    tokens = [" D", "ear", " D", "r", ".", " than", "k"]
    timestamps = [1.52, 1.68, 1.92, 2.0, 2.16, 3.04, 3.2]
    logprobs = [-0.1, -0.2, -0.05, -0.05, -0.01, -0.7, -0.1]
    text = "Dear Dr. thank"


class _Model:
    def __init__(self):
        self.calls = []

    def recognize(self, audio, sample_rate=16000, **kw):
        self.calls.append((len(audio), sample_rate, kw))
        return " Dear Dr. thank "

    def with_timestamps(self):
        model = self

        class Timed:
            def recognize(self, audio, sample_rate=16000, **kw):
                model.calls.append(("timed", len(audio)))
                return _Timed()
        return Timed()


def test_tokens_become_words_with_times():
    words = words_from_tokens(_Timed.tokens, _Timed.timestamps, _Timed.logprobs, audio_s=3.25)
    assert [w[0] for w in words] == [" Dear", " Dr.", " thank"]
    assert words[0][1:] == (1.52, 1.92) and words[1][1:] == (1.92, 3.04)
    assert words[2][2] == 3.25                       # the last word cannot end after the audio
    quick = words_from_tokens(_Timed.tokens, _Timed.timestamps, _Timed.logprobs, 3.25, with_probability=True)
    assert len(quick[0]) == 4 and abs(quick[2][3] - float(np.exp(-0.7))) < 1e-6   # weakest token of the word


def test_engine_wraps_a_model_and_ignores_the_prompt():
    model = _Model()
    engine = OnnxAsrEngine("parakeet", device="cpu", model=model)
    audio = np.zeros(16000, np.float32)
    assert engine.transcribe(audio, prompt="Vocabulary: perindopril") == "Dear Dr. thank"
    assert model.calls[-1] == (16000, 16000, {})
    assert "".join(w for w, _a, _b in engine.transcribe_words(audio)).strip() == "Dear Dr. thank"
    assert engine.transcribe(np.zeros(0, np.float32)) == ""
    assert engine.config.model == "nemo-parakeet-tdt-0.6b-v2"


def test_canary_has_no_word_timings_so_the_pipeline_stays_classic():
    engine = OnnxAsrEngine("canary", device="cpu", model=_Model())
    assert not hasattr(engine, "transcribe_words")
    engine.transcribe(np.zeros(160, np.float32))
    assert engine.model.calls[-1][2] == {"language": "en"}


def test_medasr_brace_markers_become_spoken_words():
    assert spoken_markers("clear {period} {new paragraph} soft {comma} non tender{period}{newline}plan {colon} rest") == \
        "clear period, new paragraph, soft comma, non tender period, new line, plan colon, rest"
    import voice_commands
    assert voice_commands.apply(spoken_markers("[PLAN] rest {period} {open quote} take with food {close quote}"),
                                lenient=True, punctuation=True) == 'Plan: rest. "take with food"'

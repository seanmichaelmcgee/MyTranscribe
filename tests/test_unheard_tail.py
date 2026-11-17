"""A word stranded at the end of a chunk is handed to the next chunk; safe contractions are written out."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pause_flow as pf  # noqa: E402
from text_fixes import expand_contractions  # noqa: E402

SR = 16000


def audio(*parts):
    """(seconds, level) stretches of noise -> float32 samples."""
    rng = np.random.default_rng(0)
    return np.concatenate([rng.normal(0, level, int(s * SR)) for s, level in parts]).astype(np.float32)


WORDS = [(" Creatinine", 0.2, 0.9), (" was", 0.9, 1.1), (" 88.", 1.1, 1.6), (" New", 2.0, 2.2), (" paragraph.", 2.2, 2.8)]


def test_sound_after_the_last_word_is_carried():
    # speech to 2.8 s, a pause, then 0.5 s of an undecoded word ("Plan"), cut at 4.0 s
    chunk = audio((2.8, 0.1), (0.5, 0.002), (0.5, 0.1), (0.2, 0.002))
    start = pf.unheard_tail(WORDS, chunk, SR, max_carry_s=6.0)
    assert start is not None and 2.6 <= start <= 2.8


def test_quiet_tail_is_not_carried():
    chunk = audio((2.8, 0.1), (1.2, 0.002))
    assert pf.unheard_tail(WORDS, chunk, SR, max_carry_s=6.0) is None


def test_a_click_is_not_a_word():
    chunk = audio((2.8, 0.1), (0.6, 0.002), (0.1, 0.1), (0.5, 0.002))
    assert pf.unheard_tail(WORDS, chunk, SR, max_carry_s=6.0) is None


def test_no_words_or_no_tail():
    assert pf.unheard_tail([], audio((1.0, 0.1)), SR, 6.0) is None
    assert pf.unheard_tail(WORDS, audio((2.9, 0.1)), SR, 6.0) is None


@pytest.mark.parametrize("raw, want", [
    ("I'd be grateful for your opinion.", "I would be grateful for your opinion."),
    ("I'd appreciate your assessment.", "I would appreciate your assessment."),
    ("There's no family history of melanoma.", "There is no family history of melanoma."),
    ("It's been 3 months.", "It has been 3 months."),
    ("She's taking iron daily.", "She is taking iron daily."),
])
def test_certain_contractions_written_out(raw, want):
    assert expand_contractions(raw) == want


@pytest.mark.parametrize("text", [
    "She didn't lose consciousness.",
    "He'd fallen twice before.",                 # "he had": not certain from one word, left as said
    "The patient's mother has migraine.",
    "It's improved since the last visit.",       # "has" or "is": left as said
    "I would be grateful.",
])
def test_other_contractions_left_as_said(text):
    assert expand_contractions(text) == text

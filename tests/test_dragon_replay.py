"""dragon_replay: the parts that need neither Dragon nor a sound card."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import dragon_replay as dr  # noqa: E402


def _bar(button_bgr, height=50, width=55):
    """A dark-blue strip with a round button of the given colour, like Dragon's bar."""
    px = np.zeros((height, width, 3), np.uint8)
    px[:] = (140, 90, 30)
    yy, xx = np.ogrid[:height, :width]
    px[(yy - height // 2) ** 2 + (xx - 25) ** 2 <= 18 ** 2] = button_bgr
    return px


def test_green_button_is_on():
    assert dr.classify_mic(_bar((60, 190, 110))) == "on"


def test_red_button_is_off():
    assert dr.classify_mic(_bar((50, 50, 220))) == "off"


def test_anything_else_is_unknown():
    assert dr.classify_mic(_bar((140, 90, 30))) == "unknown"          # no button visible
    assert dr.classify_mic(_bar((200, 200, 200))) == "unknown"        # greyed out
    half = _bar((60, 190, 110))
    half[:, 25:] = _bar((50, 50, 220))[:, 25:]                        # both colours: something covers it
    assert dr.classify_mic(half) == "unknown"


def test_scaled_bar_classifies_the_same():
    assert dr.classify_mic(np.kron(_bar((60, 190, 110)), np.ones((2, 2, 1), np.uint8))) == "on"


def test_clean_text_normalises_notepad_output():
    raw = b"\xef\xbb\xbfFirst line.\r\n\r\nSecond paragraph.\r\n"
    assert dr.clean_text(raw) == "First line.\n\nSecond paragraph."


def test_pcm16_clips_and_scales():
    out = np.frombuffer(dr.pcm16(np.array([0.0, 1.0, -2.0, 0.5], np.float32)), "<i2")
    assert list(out) == [0, 32767, -32767, 16383]


def test_cell_name():
    assert dr.cell_name("rec_a", "pause4") == "rec_a__pause4"

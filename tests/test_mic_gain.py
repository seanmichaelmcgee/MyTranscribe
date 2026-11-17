"""Microphone gain (Options): the factor, the int16 maths, and that the whole pipeline hears it."""

import numpy as np
import pytest

from conftest import wait_for
from fakes import ArrayStream, FakeEngine

import chunked_transcriber as ct
import settings as st


@pytest.mark.parametrize("value, db", [(50, 0.0), (0, -20.0), (100, 20.0), (75, 10.0), (25, -10.0)])
def test_slider_maps_to_decibels(value, db):
    assert 20 * np.log10(ct.gain_from_slider(value)) == pytest.approx(db)


@pytest.mark.parametrize("bad", [None, "x", -10, 400])
def test_slider_values_out_of_range_are_safe(bad):
    g = ct.gain_from_slider(bad)
    assert ct.gain_from_slider(0) <= g <= ct.gain_from_slider(100)


def test_unity_gain_leaves_the_bytes_alone():
    data = np.array([1, -2, 300], dtype=np.int16).tobytes()
    assert ct.apply_gain(data, 1.0) is data


def test_gain_scales_and_clips_instead_of_wrapping():
    data = np.array([1000, -1000, 20000, -20000], dtype=np.int16).tobytes()
    out = np.frombuffer(ct.apply_gain(data, 2.0), dtype=np.int16)
    assert list(out) == [2000, -2000, 32767, -32768]


def test_setting_default_and_bad_values(tmp_path):
    assert st.Settings().mic_gain == 50
    assert st.Settings(mic_gain="loud").clean().mic_gain == 50
    assert st.Settings(mic_gain=250).clean().mic_gain == 100
    s = st.Settings(mic_gain=70)
    st.save(s, tmp_path / "s.json")
    assert st.load(tmp_path / "s.json", env={}).mic_gain == 70


def test_quiet_input_is_heard_once_the_gain_is_raised():
    """A recording below the silence threshold is skipped at 50 and transcribed at 100."""
    t = np.arange(16000 * 2) / 16000
    quiet = (np.sin(2 * np.pi * 220 * t) * 60).astype(np.int16)    # RMS ~42 < LEVEL_THRESHOLD_RMS 80

    def run(gain_value):
        engine = FakeEngine()
        tr = ct.ChunkedTranscriber(engine, stream_factory=lambda: (ArrayStream(quiet), None))
        tr.gain = ct.gain_from_slider(gain_value)
        tr.start_recording()
        assert wait_for(lambda: not tr.recording, timeout=5)
        tr.stop_recording()
        assert tr.wait_until_idle(5)
        return engine

    assert run(50).calls == []
    assert len(run(100).calls) >= 1


def test_options_round_trip(qapp):
    from options_dialog import OptionsDialog, gain_text
    d = OptionsDialog(st.Settings(mic_gain=65))
    assert d.mic_gain.value() == 65
    d.mic_gain.setValue(30)
    assert d.result_settings().mic_gain == 30
    assert gain_text(50) == "50 · unchanged" and gain_text(75) == "75 · +10 dB" and gain_text(25) == "25 · −10 dB"


def test_window_applies_the_gain(qapp, tmp_path, monkeypatch):
    import gui_qt
    import gui_med
    from dataclasses import replace
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    w = gui_med.MedTranscriptionWindow(
        engine_factory=FakeEngine, stream_factory=lambda: (ArrayStream(np.zeros(10, np.int16)), None),
        base_prompt="", text_pipeline=(None, None), settings=st.Settings(mic_gain=75),
        settings_path=tmp_path / "s.json", install_hooks=False)
    try:
        assert wait_for(lambda: w.ready, app=qapp)
        assert w._transcriber.gain == pytest.approx(ct.gain_from_slider(75))
        w.apply_settings(replace(w._settings, mic_gain=50))
        assert w._transcriber.gain == 1.0
    finally:
        w.close()


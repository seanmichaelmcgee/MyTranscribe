"""gui_med: background load, non-blocking stop, clipboard, auto-paste (Qt under Xvfb)."""

import time

import numpy as np
import pytest

from conftest import wait_for
from fakes import ArrayStream, EndlessStream, FakeEngine, speech_like


@pytest.fixture
def make_window(qapp, monkeypatch):
    import gui_qt
    import gui_med
    import phi_clipboard
    # No real global keyboard hook in tests (and avoids its 2 s shutdown join).
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    pastes = []
    monkeypatch.setattr(phi_clipboard, "send_paste", lambda *a, **k: pastes.append(time.time()))
    monkeypatch.setattr(phi_clipboard, "modifiers_held", lambda *a, **k: False)
    windows = []

    def make(engine=None, stream=None, autopaste=False, engine_factory=None):
        engine = engine or FakeEngine()
        stream = stream or EndlessStream(speech_like(3), pace_s=0.002)
        w = gui_med.MedTranscriptionWindow(
            engine_factory=engine_factory or (lambda: engine),
            stream_factory=lambda: (stream, None),
            autopaste=autopaste, base_prompt="Vocab.",
        )
        w._chime.play_start = w._chime.play_end = lambda: None
        w.pastes = pastes
        windows.append(w)
        assert wait_for(lambda: w.ready or w._load_error, app=qapp)
        return w

    yield make
    for w in windows:
        w.close()


def finish(w, qapp, timeout=10):
    return wait_for(lambda: not w._finishing, timeout=timeout, app=qapp)


def test_buttons_disabled_until_model_loaded(qapp, make_window):
    import gui_med
    import threading
    gate = threading.Event()

    def slow_factory():
        gate.wait(5)
        return FakeEngine()
    w = gui_med.MedTranscriptionWindow(engine_factory=slow_factory,
                                       stream_factory=lambda: (None, None), base_prompt="")
    try:
        qapp.processEvents()
        assert not w._start_btn.isEnabled() and "Loading" in w._text_area.toPlainText()
        w._on_space_pressed()                     # ignored while loading
        assert w._state.name == "IDLE"
        gate.set()
        assert wait_for(lambda: w.ready, app=qapp)
        assert w._start_btn.isEnabled() and w._long_btn.isEnabled()
    finally:
        w.close()


def test_load_failure_is_shown(qapp, make_window):
    def bad():
        raise RuntimeError("Library cudnn_ops64_9.dll is not found")
    w = make_window(engine_factory=bad)
    assert wait_for(lambda: "cudnn" in w._text_area.toPlainText(), app=qapp)
    assert not w.ready and not w._start_btn.isEnabled()


def test_record_stop_copies_to_clipboard(qapp, make_window):
    w = make_window(engine=FakeEngine(text_fn=lambda i, a: f"Sentence {i}."))
    w._transcriber.chunk_target_s = 0.5
    w._on_start_clicked()
    assert w._state.name == "NORMAL_RECORDING" and w._stop_btn.isEnabled()
    assert wait_for(lambda: "Sentence 0." in w._text_area.toPlainText(), app=qapp)   # live text
    w._on_stop_clicked()
    assert finish(w, qapp)
    text = w._text_area.toPlainText()
    assert text.startswith("Sentence 0. Sentence 1.")
    assert qapp.clipboard().text() == text
    assert w._start_btn.isEnabled() and not w._stop_btn.isEnabled()
    assert w.pastes == []                       # auto-paste off by default


def test_stop_does_not_block_gui_with_slow_engine(qapp, make_window):
    w = make_window(engine=FakeEngine(delay_s=1.5))
    w._on_start_clicked()
    wait_for(lambda: False, timeout=0.3, app=qapp)
    t0 = time.perf_counter()
    w._on_stop_clicked()
    assert time.perf_counter() - t0 < 0.5
    assert w._finishing and not w._start_btn.isEnabled()
    assert "Finishing transcription" in w._text_area.toPlainText()
    w._on_space_pressed()                       # ignored while finishing
    w.on_hotkey()
    assert w._state.name == "IDLE"
    assert finish(w, qapp)
    assert w._start_btn.isEnabled()


def test_autopaste_after_hotkey_stop_only(qapp, make_window, monkeypatch):
    w = make_window(autopaste=True)
    raised = []
    monkeypatch.setattr(w, "raise_", lambda: raised.append(1))
    w.on_hotkey()                               # start: must NOT steal focus
    assert w._state.name == "NORMAL_RECORDING" and raised == []
    wait_for(lambda: False, timeout=0.2, app=qapp)
    w.on_hotkey()                               # stop via hotkey
    assert finish(w, qapp)
    assert wait_for(lambda: len(w.pastes) == 1, timeout=2, app=qapp)

    w._on_start_clicked()
    wait_for(lambda: False, timeout=0.2, app=qapp)
    w._on_stop_clicked()                        # button stop: focus is on us, don't paste
    assert finish(w, qapp)
    wait_for(lambda: False, timeout=0.5, app=qapp)
    assert len(w.pastes) == 1


def test_autopaste_waits_for_modifier_release(qapp, make_window, monkeypatch):
    import phi_clipboard
    held = {"v": True}
    monkeypatch.setattr(phi_clipboard, "modifiers_held", lambda *a, **k: held["v"])
    w = make_window(autopaste=True)
    w.on_hotkey()
    wait_for(lambda: False, timeout=0.2, app=qapp)
    w.on_hotkey()
    assert finish(w, qapp)
    wait_for(lambda: False, timeout=0.5, app=qapp)
    assert w.pastes == []                       # still holding Ctrl/Alt
    held["v"] = False
    assert wait_for(lambda: len(w.pastes) == 1, timeout=2, app=qapp)


def test_empty_result_preserves_clipboard(qapp, make_window):
    qapp.clipboard().setText("previous letter")
    w = make_window(stream=EndlessStream(np.zeros(16000, dtype=np.int16), pace_s=0.002))
    w._on_start_clicked()
    wait_for(lambda: False, timeout=0.2, app=qapp)
    w._on_stop_clicked()
    assert finish(w, qapp)
    assert qapp.clipboard().text() == "previous letter"


def test_capture_end_auto_finalizes(qapp, make_window):
    w = make_window(stream=ArrayStream(speech_like(1)))     # finite: ends by itself
    w._on_start_clicked()
    assert wait_for(lambda: w._state.name == "IDLE" and not w._finishing, timeout=5, app=qapp)
    assert qapp.clipboard().text() == "chunk0"


def test_long_mode_shows_placeholder(qapp, make_window):
    w = make_window()
    w._on_long_clicked()
    assert wait_for(lambda: "long mode" in w._text_area.toPlainText(), app=qapp)
    w._on_space_pressed()                       # space ignored in long mode (UX §4.1)
    assert w._state.name == "LONG_RECORDING"
    w._on_stop_clicked()
    assert finish(w, qapp)


def test_mic_open_failure_message(qapp, make_window):
    w = make_window()
    def bad():
        raise OSError(-9996, "Invalid input device (no default output device)")
    w._transcriber._stream_factory = bad
    w._on_start_clicked()
    assert w._state.name == "IDLE"
    assert "Could not open the microphone" in w._text_area.toPlainText()

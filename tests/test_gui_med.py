"""gui_med: background load, non-blocking stop, verified clipboard, auto-paste, triggers."""

import time

import numpy as np
import pytest

from conftest import wait_for
from fakes import ArrayStream, EndlessStream, FakeClipboard, FakeEngine, speech_like


@pytest.fixture
def make_window(qapp, monkeypatch, tmp_path):
    import gui_qt
    import gui_med
    import phi_clipboard
    from settings import Settings
    # No real global keyboard hook in tests (and avoids its 2 s shutdown join).
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    pastes = []
    monkeypatch.setattr(phi_clipboard, "send_paste", lambda *a, **k: pastes.append(time.time()))
    monkeypatch.setattr(phi_clipboard, "modifiers_held", lambda *a, **k: False)
    windows = []

    def make(engine=None, stream=None, autopaste=False, engine_factory=None, clip=None, settings=None,
             mic_warmup_s=None):
        engine = engine or FakeEngine()
        stream = stream or EndlessStream(speech_like(3), pace_s=0.002)
        w = gui_med.MedTranscriptionWindow(
            engine_factory=engine_factory or (lambda: engine),
            stream_factory=lambda: (stream, None),
            autopaste=autopaste, base_prompt="Vocab.", text_pipeline=(None, None),
            settings=settings or Settings(start_compact=False),
            settings_path=tmp_path / "settings.json", install_hooks=False, mic_warmup_s=mic_warmup_s,
        )
        chimes = []
        w._chime._inner = type("Chime", (), {"play_start": lambda s: chimes.append("start"),
                                             "play_end": lambda s: chimes.append("end"),
                                             "cleanup": lambda s: None})()
        w.chimes = chimes
        w.clip = clip if clip is not None else FakeClipboard()
        w._clipboard = lambda: w.clip
        w._clipboard_seq = w.clip.sequence                 # fake clipboard's own counter
        w.pastes = pastes
        windows.append(w)
        assert wait_for(lambda: w.ready or w._load_error, app=qapp)
        return w

    yield make
    for w in windows:
        w.close()


def finish(w, qapp, timeout=10):
    return wait_for(lambda: not w._finishing, timeout=timeout, app=qapp)


def record_and_stop(w, qapp, via_hotkey=False, seconds=0.2):
    (w.on_hotkey if via_hotkey else w._on_start_clicked)()
    wait_for(lambda: False, timeout=seconds, app=qapp)
    (w.on_hotkey if via_hotkey else w._on_stop_clicked)()
    assert finish(w, qapp)


def test_buttons_disabled_until_model_loaded(qapp, make_window, tmp_path):
    import gui_med
    import threading
    from settings import Settings
    gate = threading.Event()

    def slow_factory():
        gate.wait(5)
        return FakeEngine()
    w = gui_med.MedTranscriptionWindow(engine_factory=slow_factory,
                                       stream_factory=lambda: (None, None), base_prompt="",
                                       text_pipeline=(None, None), settings=Settings(),
                                       settings_path=tmp_path / "s.json", install_hooks=False)
    try:
        qapp.processEvents()
        assert not w._start_btn.isEnabled() and "Loading" in w._text_area.toPlainText()
        assert not w._toggle_btn.isEnabled() and "Loading" in w._toggle_btn.text()
        w._on_space_pressed()                     # ignored while loading
        assert w._state.name == "IDLE"
        gate.set()
        assert wait_for(lambda: w.ready, app=qapp)
        assert w._start_btn.isEnabled() and w._long_btn.isEnabled() and w._toggle_btn.isEnabled()
    finally:
        w.close()


def test_load_failure_is_shown(qapp, make_window):
    def bad():
        raise RuntimeError("Library cudnn_ops64_9.dll is not found")
    w = make_window(engine_factory=bad)
    assert wait_for(lambda: "cudnn" in w._text_area.toPlainText(), app=qapp)
    assert not w.ready and not w._start_btn.isEnabled() and not w._toggle_btn.isEnabled()


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
    assert wait_for(lambda: w.clip.text() == text, app=qapp)
    assert w.copy_ok is True and "Copied" in w._status_text.text()
    assert w._start_btn.isEnabled() and not w._stop_btn.isEnabled()
    assert w.pastes == []                       # auto-paste off by default


def test_toggle_button_follows_state(qapp, make_window):
    w = make_window()
    assert w._toggle_btn.text() == "Start dictation" and w._toggle_btn.isEnabled()
    w._on_toggle_clicked()
    assert w._state.name == "NORMAL_RECORDING"
    assert w._toggle_btn.text() == "Stop" and w._toggle_btn.property("recording") is True
    assert "Recording" in w._status_text.text() and not w._copy_btn.isEnabled()
    assert not w._options_btn.isEnabled()        # no hook rebuild mid-recording
    w._on_toggle_clicked()
    assert w._state.name == "IDLE"
    assert finish(w, qapp)
    assert w._toggle_btn.text() == "Start dictation" and w._copy_btn.isEnabled()
    assert w._options_btn.isEnabled()


def test_stop_does_not_block_gui_with_slow_engine(qapp, make_window):
    w = make_window(engine=FakeEngine(delay_s=1.5))
    w._on_start_clicked()
    wait_for(lambda: False, timeout=0.3, app=qapp)
    t0 = time.perf_counter()
    w._on_stop_clicked()
    assert time.perf_counter() - t0 < 0.5
    assert w._finishing and not w._start_btn.isEnabled()
    assert "Finishing transcription" in w._text_area.toPlainText()
    assert w._toggle_btn.text() == "Finishing…" and not w._toggle_btn.isEnabled()
    w._on_space_pressed()                       # ignored while finishing
    w.on_hotkey()
    assert w._state.name == "IDLE"
    assert finish(w, qapp)
    assert w._start_btn.isEnabled()


def test_hotkey_start_never_steals_focus(qapp, make_window, monkeypatch):
    w = make_window(autopaste=False)
    raised = []
    monkeypatch.setattr(w, "raise_", lambda: raised.append(1))
    monkeypatch.setattr(w, "activateWindow", lambda: raised.append(2))
    w.on_hotkey()
    assert w._state.name == "NORMAL_RECORDING" and raised == []


def test_autopaste_after_hotkey_stop_only(qapp, make_window, monkeypatch):
    w = make_window(autopaste=True)
    raised = []
    monkeypatch.setattr(w, "raise_", lambda: raised.append(1))
    record_and_stop(w, qapp, via_hotkey=True)
    assert raised == []
    assert wait_for(lambda: len(w.pastes) == 1, timeout=2, app=qapp)

    record_and_stop(w, qapp)                    # button stop: focus is on us, don't paste
    wait_for(lambda: False, timeout=0.5, app=qapp)
    assert len(w.pastes) == 1


def test_autopaste_waits_for_modifier_release(qapp, make_window, monkeypatch):
    import phi_clipboard
    held = {"v": True}
    monkeypatch.setattr(phi_clipboard, "modifiers_held", lambda *a, **k: held["v"])
    w = make_window(autopaste=True)
    record_and_stop(w, qapp, via_hotkey=True)
    wait_for(lambda: False, timeout=0.5, app=qapp)
    assert w.pastes == []                       # still holding Ctrl/Alt
    held["v"] = False
    assert wait_for(lambda: len(w.pastes) == 1, timeout=2, app=qapp)


def test_busy_clipboard_never_pastes_stale_text(qapp, make_window):
    """The safety fix: a failed copy must not paste the PREVIOUS clipboard contents."""
    clip = FakeClipboard("other patient's note", reject_writes=-1)
    w = make_window(autopaste=True, clip=clip)
    record_and_stop(w, qapp, via_hotkey=True)
    assert wait_for(lambda: w.copy_ok is False, timeout=3, app=qapp)
    wait_for(lambda: False, timeout=0.5, app=qapp)
    assert w.pastes == []
    assert clip.text() == "other patient's note"
    assert clip.writes == 6                     # retried, then gave up
    assert "Not copied" in w._status_text.text() and w._copy_btn.property("attention") is True
    assert w._text_area.toPlainText().startswith("chunk0")   # text kept in the window

    clip.reject_writes = 0                      # clipboard free again: Copy button works
    w._on_copy_clicked()
    assert wait_for(lambda: w.copy_ok is True, app=qapp)
    assert clip.text() == w._text_area.toPlainText()
    assert w.pastes == []                       # manual Copy never auto-pastes


def test_briefly_busy_clipboard_retries_then_pastes(qapp, make_window):
    clip = FakeClipboard("old", reject_writes=2)
    w = make_window(autopaste=True, clip=clip)
    record_and_stop(w, qapp, via_hotkey=True)
    assert wait_for(lambda: len(w.pastes) == 1, timeout=3, app=qapp)
    assert clip.writes == 3 and clip.text().startswith("chunk0")


def test_clipboard_changed_before_paste_is_not_pasted(qapp, make_window, monkeypatch):
    import phi_clipboard
    held = {"v": True}
    monkeypatch.setattr(phi_clipboard, "modifiers_held", lambda *a, **k: held["v"])
    w = make_window(autopaste=True)
    record_and_stop(w, qapp, via_hotkey=True)
    assert wait_for(lambda: w.copy_ok is True, app=qapp)
    w.clip.setText("something the user copied meanwhile")
    held["v"] = False
    wait_for(lambda: False, timeout=0.6, app=qapp)
    assert w.pastes == [] and "Not pasted" in w._status_text.text()


def test_empty_result_preserves_clipboard(qapp, make_window):
    clip = FakeClipboard("previous letter")
    w = make_window(stream=EndlessStream(np.zeros(16000, dtype=np.int16), pace_s=0.002), clip=clip)
    record_and_stop(w, qapp)
    assert clip.text() == "previous letter" and clip.writes == 0


def test_capture_end_auto_finalizes(qapp, make_window):
    w = make_window(stream=ArrayStream(speech_like(1)))     # finite: ends by itself
    w._on_start_clicked()
    assert wait_for(lambda: w._state.name == "IDLE" and not w._finishing, timeout=5, app=qapp)
    assert wait_for(lambda: w.clip.text() == "chunk0", app=qapp)


def test_voice_commands_reach_clipboard(qapp, make_window):
    from settings import Settings
    said = "Book review in 2 weeks. New line, open quotes, follow up x-ray, close quotes."
    w = make_window(engine=FakeEngine(text_fn=lambda i, a: said if i == 0 else ""),
                    stream=ArrayStream(speech_like(1)))
    w._on_start_clicked()
    assert wait_for(lambda: w._state.name == "IDLE" and not w._finishing, timeout=5, app=qapp)
    assert wait_for(lambda: w.clip.text() == 'Book review in 2 weeks.\n"Follow up x-ray".', app=qapp)

    w2 = make_window(engine=FakeEngine(text_fn=lambda i, a: said if i == 0 else ""),
                     stream=ArrayStream(speech_like(1)), settings=Settings(start_compact=False,
                                                                           voice_commands=False))
    w2._on_start_clicked()
    assert wait_for(lambda: w2._state.name == "IDLE" and not w2._finishing, timeout=5, app=qapp)
    assert wait_for(lambda: w2.clip.text() == said, app=qapp)


def test_no_long_record_button(qapp, make_window):
    w = make_window()
    w.show()
    qapp.processEvents()
    assert not w._long_btn.isVisible()          # one button handles any length (≤ 1 h)


def test_mic_open_failure_message(qapp, make_window):
    w = make_window()
    def bad():
        raise OSError(-9996, "Invalid input device (no default output device)")
    w._transcriber._stream_factory = bad
    w._on_start_clicked()
    assert w._state.name == "IDLE"
    assert "Could not open the microphone" in w._text_area.toPlainText()


def test_mouse_toggle_mode(qapp, make_window):
    w = make_window()                            # defaults: F9 hold, mouse forward toggle
    w._triggers.handle("mouse", "down")
    assert wait_for(lambda: w._state.name == "NORMAL_RECORDING", app=qapp)
    w._triggers.handle("mouse", "up")            # toggle mode: release does nothing
    wait_for(lambda: False, timeout=0.2, app=qapp)
    assert w._state.name == "NORMAL_RECORDING"
    w._triggers.handle("mouse", "down")
    assert wait_for(lambda: w._state.name == "IDLE", app=qapp)
    assert finish(w, qapp)


def test_f9_hold_to_talk(qapp, make_window):
    w = make_window()
    w._triggers.handle("key", "down")
    w._triggers.handle("key", "down")            # keyboard auto-repeat while held
    assert wait_for(lambda: w._state.name == "NORMAL_RECORDING", app=qapp)
    wait_for(lambda: False, timeout=0.2, app=qapp)
    assert w._state.name == "NORMAL_RECORDING"
    w._triggers.handle("key", "up")
    assert wait_for(lambda: w._state.name == "IDLE", app=qapp)
    assert finish(w, qapp)


def test_hold_press_while_recording_does_not_stop(qapp, make_window):
    w = make_window()
    w._on_toggle_clicked()                       # started with the button
    w._triggers.handle("key", "down")            # hold-to-talk press only ever starts
    wait_for(lambda: False, timeout=0.2, app=qapp)
    assert w._state.name == "NORMAL_RECORDING"
    w._triggers.handle("key", "up")              # ...but releasing stops (talk ended)
    assert wait_for(lambda: w._state.name == "IDLE", app=qapp)
    assert finish(w, qapp)


def test_recording_light_green_on_red_off(qapp, make_window):
    w = make_window()
    assert w.rec_light_on is False and "#C8322B" in w._rec_light.styleSheet()
    w._triggers.handle("key", "down")
    assert wait_for(lambda: w.rec_light_on is True, app=qapp)
    assert "#2E9E4F" in w._rec_light.styleSheet()
    w._triggers.handle("key", "up")
    assert wait_for(lambda: w.rec_light_on is False, app=qapp)
    assert finish(w, qapp)
    w._on_toggle_clicked()
    assert w.rec_light_on is True                # button start too
    w._on_toggle_clicked()
    assert w.rec_light_on is False
    assert finish(w, qapp)


def test_mic_warmup_amber_then_green_with_chime(qapp, make_window):
    """Mic opened per recording: amber until it's really listening, then green + chime."""
    w = make_window(mic_warmup_s=0.3, stream=EndlessStream(speech_like(3), pace_s=0.064))  # ~real time
    w._on_toggle_clicked()
    assert w._state.name == "NORMAL_RECORDING"
    assert w.rec_light_state == "warm" and "Starting mic" in w._status_text.text()
    assert w.chimes == []                                   # no "talk now" chime yet
    assert wait_for(lambda: w.rec_light_state == "on", timeout=3, app=qapp)
    assert w.chimes == ["start"] and w._status_text.text() == "Recording"
    w._on_toggle_clicked()
    assert w.rec_light_state == "off" and w.chimes == ["start", "end"]
    assert finish(w, qapp)


def test_no_warmup_when_mic_kept_ready(qapp, make_window):
    w = make_window()                                       # injected stream: like a ready mic
    w._on_toggle_clicked()
    assert w.rec_light_state == "on" and w.chimes == ["start"]
    w._on_toggle_clicked()
    assert finish(w, qapp)


def test_ready_mic_feeds_recordings_with_preroll(qapp, tmp_path, monkeypatch):
    """Real wiring: keep_mic_ready=True uses ReadyMic sessions, device stays open."""
    import gui_qt
    import gui_med
    import mic_ready
    from settings import Settings
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    opened = []

    def open_stream():
        s = EndlessStream(speech_like(3), pace_s=0.004)
        opened.append(s)
        return s, None
    monkeypatch.setattr(gui_med, "ReadyMic", lambda: mic_ready.ReadyMic(open_stream=open_stream))
    w = gui_med.MedTranscriptionWindow(engine_factory=FakeEngine, autopaste=False, base_prompt="",
                                       text_pipeline=(None, None), settings=Settings(start_compact=False),
                                       settings_path=tmp_path / "s.json", install_hooks=False)
    w._chime._inner = type("C", (), {"play_start": lambda s: None, "play_end": lambda s: None,
                                     "cleanup": lambda s: None})()
    w._clipboard = lambda: FakeClipboard()
    w._clipboard_seq = None
    try:
        assert wait_for(lambda: w.ready, app=qapp) and w._ready_mic is not None
        assert wait_for(lambda: w._ready_mic.reads > 10, app=qapp)
        for _ in range(2):
            w._on_toggle_clicked()
            assert w.rec_light_state == "on"                # no warm-up needed
            wait_for(lambda: False, timeout=0.3, app=qapp)
            w._on_toggle_clicked()
            assert finish(w, qapp)
        assert len(opened) == 1                             # one device open for both recordings
    finally:
        w.close()
    assert w._ready_mic is not None and not w._ready_mic._running


def _live_window(make_window, qapp, fg):
    from settings import Settings
    w = make_window(engine=FakeEngine(text_fn=lambda i, a: f"Piece {i}."),
                    settings=Settings(start_compact=False, live_insert=True))
    w._foreground = lambda: fg["hwnd"]
    w._transcriber.chunk_target_s = 0.5
    return w


def test_live_insert_pastes_pieces_then_copies_full_text(qapp, make_window):
    fg = {"hwnd": 4242}                                     # the EMR window has focus
    w = _live_window(make_window, qapp, fg)
    w.on_hotkey()
    assert wait_for(lambda: len(w.inserted_pieces) >= 2, timeout=5, app=qapp)
    w.on_hotkey()
    assert finish(w, qapp)
    assert wait_for(lambda: w.copy_ok is True, timeout=3, app=qapp)
    wait_for(lambda: False, timeout=0.5, app=qapp)
    joined = "".join(w.inserted_pieces)
    full = w._text_area.toPlainText()
    assert w.inserted_pieces[0] == "Piece 0." and w.inserted_pieces[1] == " Piece 1."
    assert joined == full                                  # everything inserted, in order, spaced
    assert w.clip.text() == full                           # clipboard ends with the full text
    assert len(w.pastes) == len(w.inserted_pieces)         # no extra paste of the full text
    assert "Inserted at cursor" in w._status_text.text()


def test_live_insert_holds_when_focus_moves_and_never_types_into_itself(qapp, make_window):
    fg = {"hwnd": 4242}
    w = _live_window(make_window, qapp, fg)
    w.on_hotkey()
    assert wait_for(lambda: len(w.inserted_pieces) >= 1, timeout=5, app=qapp)
    fg["hwnd"] = 9999                                      # user clicked into another app
    n = len(w.inserted_pieces)
    wait_for(lambda: False, timeout=1.5, app=qapp)
    assert len(w.inserted_pieces) == n                     # nothing typed into the other app
    w.on_hotkey()
    assert finish(w, qapp)
    assert wait_for(lambda: w.copy_ok is True, timeout=3, app=qapp)
    assert w.clip.text() == w._text_area.toPlainText()     # full text still on the clipboard
    assert "Not all inserted" in w._status_text.text()

    fg["hwnd"] = int(w.winId())                            # MyTranscribe itself in front
    w2_start = len(w.inserted_pieces)
    w.on_hotkey()
    wait_for(lambda: False, timeout=1.5, app=qapp)
    w.on_hotkey()
    assert finish(w, qapp)
    assert len(w.inserted_pieces) == w2_start              # never types into its own window


def test_live_insert_busy_clipboard_stops_inserting(qapp, make_window):
    fg = {"hwnd": 4242}
    w = _live_window(make_window, qapp, fg)
    w.clip.reject_writes = -1
    w.on_hotkey()
    wait_for(lambda: False, timeout=1.5, app=qapp)
    assert w.inserted_pieces == [] and w.pastes == []      # nothing pasted without a verified copy
    w.on_hotkey()
    assert finish(w, qapp)
    assert wait_for(lambda: w.copy_ok is False, timeout=3, app=qapp)


def test_starts_compact_and_plus_expands(qapp, make_window):
    from settings import Settings
    w = make_window(settings=Settings(start_compact=True))
    w.show()
    qapp.processEvents()
    assert w._compact and not w._text_area.isVisible() and w._compact_btn.text() == "+"
    assert w._rec_light.isVisible() and w._toggle_btn.isVisible()
    compact_h = w.height()
    w._toggle_compact()                          # "+"
    qapp.processEvents()
    assert w._text_area.isVisible() and w.height() > compact_h + 100
    w._toggle_compact()                          # "–" again
    qapp.processEvents()
    assert not w._text_area.isVisible() and w.height() <= compact_h + 5


def test_options_change_applies_and_saves(qapp, make_window, tmp_path):
    import json
    from settings import Settings
    w = make_window()
    w.apply_settings(Settings(key="f10", key_mode="toggle", mouse="none", start_compact=True))
    assert w._triggers.config.key == "f10" and w._triggers.config.key_hold is False
    assert w._triggers.config.mouse is None
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["key"] == "f10" and saved["mouse"] == "none" and saved["start_compact"] is True
    w._triggers.handle("key", "down")            # now a toggle
    assert wait_for(lambda: w._state.name == "NORMAL_RECORDING", app=qapp)
    w._triggers.handle("key", "up")
    wait_for(lambda: False, timeout=0.2, app=qapp)
    assert w._state.name == "NORMAL_RECORDING"
    w._triggers.handle("key", "down")
    assert wait_for(lambda: w._state.name == "IDLE", app=qapp)
    assert finish(w, qapp)

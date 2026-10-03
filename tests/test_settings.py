"""settings + options dialog: defaults, file round trip, env overrides, bad files, dialog result."""

import json

import settings as st


def test_defaults_when_no_file(tmp_path):
    s = st.load(tmp_path / "missing.json", env={})
    assert (s.key, s.key_mode, s.mouse, s.mouse_mode, s.start_compact) == ("f9", "hold", "x2", "toggle", True)
    t = s.triggers()
    assert t.key == "f9" and t.key_hold and t.mouse == "x2" and not t.mouse_hold


def test_round_trip_and_env_override(tmp_path):
    p = tmp_path / "sub" / "settings.json"
    st.save(st.Settings(key="pause", key_mode="toggle", mouse="none", start_compact=False), p)
    s = st.load(p, env={})
    assert (s.key, s.key_mode, s.mouse, s.start_compact) == ("pause", "toggle", "none", False)
    assert s.triggers().mouse is None
    s = st.load(p, env={"MYTRANSCRIBE_KEY": "F12", "MYTRANSCRIBE_MOUSE_MODE": "hold"})
    assert s.key == "f12" and s.mouse_mode == "hold"


def test_bad_or_hand_edited_file_falls_back(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert st.load(p, env={}) == st.Settings()
    p.write_text(json.dumps({"key": "ctrl", "key_mode": "sideways", "mouse": "left", "extra": 1}),
                 encoding="utf-8")
    s = st.load(p, env={})
    assert (s.key, s.key_mode, s.mouse) == ("f9", "hold", "x2")


def test_settings_file_never_holds_text(tmp_path):
    p = tmp_path / "settings.json"
    st.save(st.Settings(), p)
    assert set(json.loads(p.read_text(encoding="utf-8"))) == {"key", "key_mode", "mouse", "mouse_mode",
                                                              "start_compact", "accuracy", "voice_commands",
                                                              "keep_mic_ready", "live_insert"}


def test_accuracy_default_and_validation(tmp_path):
    assert st.Settings().accuracy == "best"
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"accuracy": "turbo-max"}), encoding="utf-8")
    assert st.load(p, env={}).accuracy == "best"


def test_options_dialog_result(qapp):
    from options_dialog import OptionsDialog
    d = OptionsDialog(st.Settings())
    assert d.key.currentData() == "f9" and d.key_mode.currentData() == "hold"
    assert d.mouse.currentData() == "x2" and d.mouse_mode.currentData() == "toggle"
    d.key.setCurrentIndex(d.key.findData("none"))
    assert not d.key_mode.isEnabled()                 # no key: its mode is irrelevant
    d.mouse_mode.setCurrentIndex(d.mouse_mode.findData("hold"))
    d.start_compact.setChecked(False)
    assert d.accuracy.currentData() == "best"
    d.accuracy.setCurrentIndex(d.accuracy.findData("fast"))
    r = d.result_settings()
    assert (r.key, r.mouse, r.mouse_mode, r.start_compact, r.accuracy) == ("none", "x2", "hold", False, "fast")

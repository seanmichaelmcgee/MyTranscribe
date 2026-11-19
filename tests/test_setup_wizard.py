"""Setup wizard (phase 1): settings, microphone choice and check, wizard pages, first start, re-run."""

import json
import time

import numpy as np
import pytest

from conftest import wait_for

import settings as st


# ── Settings ─────────────────────────────────────────────────────────────────
def test_new_settings_round_trip_and_bad_values(tmp_path):
    p = tmp_path / "settings.json"
    assert st.Settings().input_device == "" and st.Settings().setup_version == 0
    st.save(st.Settings(input_device="Microphone (USB Headset)", setup_version=1), p)
    s = st.load(p, env={})
    assert (s.input_device, s.setup_version) == ("Microphone (USB Headset)", 1)
    p.write_text(json.dumps({"input_device": 7, "setup_version": "x", "dictation_style": "shouting"}), encoding="utf-8")
    s = st.load(p, env={})
    assert (s.input_device, s.setup_version, s.dictation_style) == ("", 0, "")


# ── Microphone check ─────────────────────────────────────────────────────────
SR = 16000


def tone(seconds, rms, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(seconds * SR)) * rms).astype(np.float32)


def speechy(seconds, rms, seed=1):
    """Noise bursts with gaps, so frame levels vary like speech."""
    a = tone(seconds, rms, seed)
    for start in np.arange(0.4, seconds, 0.7):
        a[int(start * SR):int((start + 0.2) * SR)] *= 0.05
    return a


def test_good_level_is_left_alone():
    from mic_check import analyse
    r = analyse(tone(3, 0.0005), speechy(6, 0.05))
    assert r.heard and r.gain == 50 and r.warnings == []
    assert "good" in r.summary() and "left as the microphone sends it" in r.summary()


def test_quiet_voice_raises_gain_and_very_quiet_still_warns():
    from mic_check import analyse
    r = analyse(tone(3, 0.00005), speechy(6, 0.005))           # speech around -46 dBFS
    assert r.heard and r.gain > 50 and r.warnings == []
    r = analyse(tone(3, 0.0005), speechy(6, 0.002))            # quiet voice over a -66 dBFS room
    assert r.heard and 50 < r.gain < 100
    assert r.noise_db + r.gain_db <= -52.2 - 6 + 0.5               # the room is not lifted to "sound"
    assert any("still quiet" in w for w in r.warnings)


def test_clipping_lowers_gain_and_warns():
    from mic_check import analyse
    loud = np.clip(speechy(6, 0.6), -1, 1)
    r = analyse(tone(3, 0.001), loud)
    assert r.gain < 50 and any("top of the microphone's range" in w for w in r.warnings)


def test_nothing_heard_and_noisy_room_and_bluetooth():
    from mic_check import analyse
    r = analyse(tone(3, 0.001), tone(6, 0.001, seed=3))
    assert not r.heard and r.gain == 50 and "Privacy" in r.warnings[0]
    r = analyse(tone(3, 0.01), speechy(6, 0.05))               # background about -40 dBFS
    assert any("background is loud" in w for w in r.warnings)
    r = analyse(tone(3, 0.0005), speechy(6, 0.05), bluetooth=True)
    assert any("Bluetooth" in w for w in r.warnings)


# ── Microphone list ──────────────────────────────────────────────────────────
class FakePA:
    APIS = [{"name": "MME", "index": 0}, {"name": "Windows DirectSound", "index": 1},
            {"name": "Windows WDM-KS", "index": 2}]
    DEVICES = [
        {"name": "Microsoft Sound Mapper - Input", "hostApi": 0, "maxInputChannels": 2},
        {"name": "Microphone (Logitech G533 Gamin", "hostApi": 0, "maxInputChannels": 1},
        {"name": "Headset (OpenFit 2 by Shokz)", "hostApi": 0, "maxInputChannels": 1},
        {"name": "CABLE Output (VB-Audio Virtual ", "hostApi": 0, "maxInputChannels": 16},
        {"name": "Speakers (Realtek)", "hostApi": 0, "maxInputChannels": 0},
        {"name": "Primary Sound Capture Driver", "hostApi": 1, "maxInputChannels": 2},
        {"name": "CABLE Output (VB-Audio Virtual Cable)", "hostApi": 1, "maxInputChannels": 16},
        {"name": "Microphone (Logitech G533 Gaming Headset)", "hostApi": 1, "maxInputChannels": 1},
        {"name": "Headset (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0\r\n;(OpenFit 2 by Shokz))",
         "hostApi": 2, "maxInputChannels": 1},
    ]

    def get_default_host_api_info(self):
        return self.APIS[0]

    def get_host_api_count(self):
        return len(self.APIS)

    def get_host_api_info_by_index(self, i):
        return self.APIS[i]

    def get_device_count(self):
        return len(self.DEVICES)

    def get_device_info_by_index(self, i):
        return dict(self.DEVICES[i], index=i)

    def get_default_input_device_info(self):
        return dict(self.DEVICES[1], index=1)

    def terminate(self):
        pass


def test_microphone_list_uses_full_names_and_spots_bluetooth(monkeypatch):
    import audio_devices
    monkeypatch.setattr(audio_devices.sys, "platform", "win32")
    pa = FakePA()
    devices = audio_devices.list_inputs(pa)
    assert [d.name for d in devices] == ["Microphone (Logitech G533 Gaming Headset)", "Headset (OpenFit 2 by Shokz)",
                                         "CABLE Output (VB-Audio Virtual Cable)"]     # cut names made whole
    assert [d.bluetooth for d in devices] == [False, True, False]
    assert audio_devices.default_name(pa) == "Microphone (Logitech G533 Gaming Headset)"
    assert audio_devices.find_index(pa, "Microphone (Logitech G533 Gaming Headset)") == 1
    assert audio_devices.find_index(pa, "Microphone (Logitech G533 Gamin") == 1     # a cut name saved elsewhere
    assert audio_devices.find_index(pa, "Gone (USB)") is None
    assert audio_devices.find_index(pa, "") is None


# ── Wizard ───────────────────────────────────────────────────────────────────
class LevelStream:
    """Quiet until the panel asks for speech; paced like a microphone."""

    def __init__(self, panel_ref):
        self.panel_ref = panel_ref
        self.rng = np.random.default_rng(0)

    def read(self, n, exception_on_overflow=False):
        time.sleep(0.005)
        panel = self.panel_ref()
        rms = 1600 if panel is not None and panel._phase == "speak" else 16
        return (self.rng.standard_normal(n) * rms).clip(-32767, 32767).astype(np.int16).tobytes()

    def stop_stream(self):
        pass

    def close(self):
        pass


@pytest.fixture
def make_wizard(qapp):
    from hw_profile import HardwareInfo
    import setup_wizard
    made = []

    def make(settings=None, first_run=False, hw=None):
        holder = {}
        w = setup_wizard.SetupWizard(
            settings or st.Settings(), first_run=first_run,
            hardware=lambda: hw or HardwareInfo(cuda_device_count=1, gpu_name="NVIDIA GeForce GTX 1060 6GB",
                                                vram_mb=6144),
            devices=["Microphone (USB Headset)", "Headset (Buds)"], default_device="Microphone (USB Headset)",
            open_stream=lambda device: (LevelStream(lambda: holder.get("panel")), None),
            bluetooth=lambda name: "Buds" in name, install_hooks=False)
        holder["panel"] = w.microphone.panel
        made.append(w)
        return w

    yield make
    for w in made:
        w.done(0)


def go_to(w, page, qapp):
    w.show()
    qapp.processEvents()
    while w.currentPage() is not page:
        w.next()
        qapp.processEvents()


def test_first_start_waits_for_how_you_dictate_and_recommended_keeps_it(make_wizard, qapp):
    from PyQt6.QtWidgets import QWizard
    w = make_wizard(st.Settings(spoken_punctuation=True, key="f12"), first_run=True)
    w.show()
    qapp.processEvents()
    recommended = w.button(QWizard.WizardButton.CustomButton1)
    assert recommended.isVisible()
    assert not w.welcome.isComplete() and not recommended.isEnabled()      # nothing chosen for them
    assert not w.button(QWizard.WizardButton.NextButton).isEnabled()
    w.welcome.group.buttons()[1].card.mousePressEvent(_click())           # clicking the card chooses it
    assert w.welcome.choice() == "none" and recommended.isEnabled()
    recommended.click()
    # Natural speech keeps spoken punctuation on: a "period" that is said still becomes a mark.
    assert w.result_settings() == st.Settings(setup_version=1, spoken_punctuation=True, dictation_style="natural")


def test_recommended_after_choosing_traditional_keeps_the_marks(make_wizard, qapp):
    from PyQt6.QtWidgets import QWizard
    w = make_wizard(first_run=True)
    w.show()
    qapp.processEvents()
    w.welcome.group.buttons()[0].setChecked(True)
    assert w.welcome.every_comma.isVisible() and w.welcome.choice() == "some"
    w.welcome.every_comma.setChecked(True)
    w.button(QWizard.WizardButton.CustomButton1).click()
    r = w.result_settings()
    assert r == st.Settings(setup_version=1, spoken_punctuation=True, only_dictated_commas=True,
                            dictation_style="traditional")


def test_a_rerun_shows_natural_speech_again(make_wizard, qapp):
    s = st.Settings(spoken_punctuation=True, dictation_style="natural", setup_version=1)
    w = make_wizard(s)
    assert w.welcome.choice() == "none"
    go_to(w, w.summary, qapp)
    assert "natural speech" in w.summary.lines.text() and "Nothing changed" in w.summary.changes.text()


def _click():
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    return QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_choices_map_to_settings(make_wizard, qapp):
    w = make_wizard()
    w.show()
    qapp.processEvents()
    assert w.welcome.choice() == "none"                                 # a re-run shows the current answer
    w.welcome.group.buttons()[0].setChecked(True)                       # traditional
    w.welcome.every_comma.setChecked(True)
    go_to(w, w.computer, qapp)
    assert "GTX 1060" in w.computer.text.text() and w.computer.group.buttons()[0].isVisible()
    w.computer.group.buttons()[1].setChecked(True)                    # Faster
    go_to(w, w.microphone, qapp)
    panel = w.microphone.panel
    panel.device.setCurrentIndex(panel.device.findData("Headset (Buds)"))
    panel.gain.setValue(60)
    go_to(w, w.output, qapp)
    w.output.group.buttons()[2].setChecked(True)                      # type while I talk
    go_to(w, w.trigger_page, qapp)
    t = w.trigger_page
    t.key.setCurrentIndex(t.key.findData("f8"))
    t.key_mode.setCurrentIndex(t.key_mode.findData("toggle"))
    t.mouse.setCurrentIndex(t.mouse.findData("none"))
    go_to(w, w.summary, qapp)
    text = w.summary.lines.text()
    assert "Headset (Buds)" in text and "traditional, every comma said" in text and "F8 (toggle)" in text
    assert "Accuracy" not in w.summary.changes.text() and "Changed from before" in w.summary.changes.text()
    r = w.result_settings()
    assert (r.accuracy, r.input_device, r.mic_gain) == ("fast", "Headset (Buds)", 60)
    assert r.spoken_punctuation and r.only_dictated_commas and r.voice_commands
    assert r.live_insert and not r.autopaste
    assert (r.key, r.key_mode, r.mouse) == ("f8", "toggle", "none")
    assert r.setup_version == 1
    assert r.pause_aware and r.extra_fixes and r.engine == "whisper"   # not asked: kept


def test_rerun_with_nothing_changed_says_so(make_wizard, qapp):
    s = st.Settings(spoken_punctuation=True, autopaste=True, setup_version=1)
    w = make_wizard(s)
    assert w.welcome.choice() == "some" and not w.welcome.every_comma.isChecked()
    go_to(w, w.output, qapp)
    assert w.output.choice() == "paste"
    go_to(w, w.summary, qapp)
    assert "Nothing changed" in w.summary.changes.text()
    r = w.result_settings()
    assert r.spoken_punctuation and not r.only_dictated_commas and r.autopaste and not r.live_insert


def test_summary_names_the_model_this_pc_runs(make_wizard, qapp):
    from hw_profile import HardwareInfo
    w = make_wizard(hw=HardwareInfo(cuda_device_count=0, cpu_count=8))
    go_to(w, w.summary, qapp)
    text = w.summary.lines.text()
    assert "small.en, on the processor" in text and "large-v3" not in text
    w2 = make_wizard()                                                  # a 6 GB card: the accuracy answer
    go_to(w2, w2.summary, qapp)
    assert "most accurate (large-v3)" in w2.summary.lines.text()


def test_download_note_says_where_the_model_comes_from(monkeypatch):
    from hw_profile import HardwareInfo
    import setup_wizard
    cpu = HardwareInfo(cuda_device_count=0)
    monkeypatch.setattr(setup_wizard.engines, "bundled_model", lambda name: None)
    assert "0.5 GB" in setup_wizard.download_note(cpu) and "asks before" in setup_wizard.download_note(cpu)
    monkeypatch.setattr(setup_wizard.engines, "bundled_model", lambda name: "x" if name == "small.en" else None)
    assert "came with the installer" in setup_wizard.download_note(cpu)
    assert "3 GB" in setup_wizard.download_note(HardwareInfo(cuda_device_count=1, vram_mb=8000))


def test_options_say_accuracy_does_not_apply_without_a_graphics_card(qapp):
    from options_dialog import OptionsDialog
    d = OptionsDialog(st.Settings(), devices=["Mic"], default_device="Mic", processor_only=True)
    assert not d.accuracy.isEnabled()
    gpu = OptionsDialog(st.Settings(), devices=["Mic"], default_device="Mic")
    assert gpu.accuracy.isEnabled()


def test_hardware_descriptions():
    from hw_profile import HardwareInfo
    from setup_wizard import describe_hardware
    assert describe_hardware(None)[1] is False and "processor" in describe_hardware(None)[0]
    text, choice = describe_hardware(HardwareInfo(cuda_device_count=1, gpu_name="GTX 1050", vram_mb=4096))
    assert not choice and "large-v3-turbo" in text
    assert describe_hardware(HardwareInfo(cuda_device_count=1, gpu_name="RTX 4070", vram_mb=16376))[1]


def test_trigger_page_shows_a_press(make_wizard, qapp):
    w = make_wizard()
    go_to(w, w.trigger_page, qapp)
    t = w.trigger_page
    assert t.triggers is not None
    t.triggers.handle("key", "down")
    assert wait_for(lambda: "F9 works" in t.seen.text(), app=qapp)
    w.next()
    assert t.triggers is None                                         # listening stops on leaving the page


def test_microphone_check_sets_gain(make_wizard, qapp, monkeypatch):
    import setup_wizard
    monkeypatch.setattr(setup_wizard, "QUIET_S", 0.4)
    monkeypatch.setattr(setup_wizard, "SPEAK_S", 0.6)
    w = make_wizard()
    go_to(w, w.microphone, qapp)
    panel = w.microphone.panel
    assert wait_for(lambda: panel.monitor.running, app=qapp)
    panel.check_button.click()
    assert wait_for(lambda: panel.result is not None, timeout=5, app=qapp)
    r = panel.result
    assert r.heard and r.separation_db > 30
    assert panel.gain.value() == r.gain and panel.outcome.isVisible()
    w.next()
    assert not panel.monitor.running                                  # the microphone is let go


# ── First start, re-run, Options ─────────────────────────────────────────────
class FakeWizard:
    def __init__(self, result, accept=True):
        self.result, self.accept = result, accept

    def exec(self):
        return self.accept

    def result_settings(self):
        return self.result


def test_first_start_runs_the_wizard_once(tmp_path):
    import gui_med
    path = tmp_path / "settings.json"
    chosen = st.Settings(spoken_punctuation=True, setup_version=1)
    s = gui_med.first_start_settings(path, wizard_factory=lambda s: FakeWizard(chosen))
    assert s == chosen and st.load(path, env={}).spoken_punctuation
    assert gui_med.first_start_settings(path, wizard_factory=lambda s: pytest.fail("asked again")) is None


def test_first_start_closed_wizard_keeps_defaults(tmp_path):
    import gui_med
    path = tmp_path / "settings.json"
    s = gui_med.first_start_settings(path, wizard_factory=lambda s: FakeWizard(None, accept=False))
    assert s.setup_version == 0 and path.exists()


def test_rerun_from_options_applies_and_keeps_a_backup(qapp, monkeypatch, tmp_path):
    import gui_qt
    import gui_med
    from fakes import EndlessStream, FakeEngine, speech_like
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    stream = EndlessStream(speech_like(1), pace_s=0.002)
    w = gui_med.MedTranscriptionWindow(
        engine_factory=lambda: FakeEngine(), stream_factory=lambda: (stream, None), autopaste=False,
        base_prompt="", text_pipeline=(None, None), settings=st.Settings(start_compact=False),
        settings_path=tmp_path / "settings.json", install_hooks=False)
    try:
        assert wait_for(lambda: w.ready, app=qapp)
        assert not w.run_setup(lambda: FakeWizard(None, accept=False))
        assert w._triggers is not None and not (tmp_path / "settings.before-setup.json").exists()
        new = st.Settings(start_compact=False, spoken_punctuation=True, key="f8", setup_version=1)
        assert w.run_setup(lambda: FakeWizard(new))
        assert w._settings.spoken_punctuation and w._triggers.config.key == "f8"
        assert st.load(tmp_path / "settings.json", env={}).key == "f8"
        assert st.load(tmp_path / "settings.before-setup.json", env={}).key == "f9"
    finally:
        w.close()


def test_options_microphone_choice_and_setup_button(qapp):
    from options_dialog import OptionsDialog
    d = OptionsDialog(st.Settings(input_device="Old USB mic"), devices=["Microphone (USB Headset)"],
                      default_device="Microphone (USB Headset)")
    assert d.input_device.currentText() == "Old USB mic (not connected)"
    assert d.result_settings().input_device == "Old USB mic"
    d.input_device.setCurrentIndex(0)
    assert d.input_device.currentText() == "Windows default (Microphone (USB Headset))"
    assert d.result_settings().input_device == ""
    assert not d.requested_setup
    d.run_setup.click()
    assert d.requested_setup and d.result() == 1

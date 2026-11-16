"""Recogniser registry, the Options switch, the download question and the log window."""

import logging
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app_log  # noqa: E402
import engines  # noqa: E402
from conftest import wait_for  # noqa: E402
from fakes import FakeEngine  # noqa: E402
from test_gui_med import make_window  # noqa: E402,F401  (fixture)


# ── registry ────────────────────────────────────────────────────────────────
def test_every_engine_says_where_its_model_comes_from():
    assert engines.DEFAULT == "whisper" and set(engines.ENGINES) == {"whisper", "medasr", "parakeet", "canary"}
    for info in engines.ENGINES.values():
        assert info.source and info.size and info.licence and info.label


def test_availability_reports_missing_packages_and_the_gated_model(tmp_path):
    have = lambda name: object()                                         # noqa: E731
    none = lambda name: None                                             # noqa: E731
    assert engines.availability("whisper", find_spec=have) == (True, "")
    ok, why = engines.availability("parakeet", find_spec=none)
    assert not ok and "onnx_asr" in why
    ok, why = engines.availability("medasr", find_spec=have, env={"MYTRANSCRIBE_MEDASR_DIR": str(tmp_path)})
    assert not ok and "sign-in" in why
    (tmp_path / "model.safetensors").write_bytes(b"x")
    (tmp_path / "integrity.json").write_text("{}")
    assert engines.availability("medasr", find_spec=have, env={"MYTRANSCRIBE_MEDASR_DIR": str(tmp_path)})[0]
    assert engines.availability("nope") == (False, "unknown recogniser")


def test_a_missing_model_becomes_a_question_not_a_download(monkeypatch):
    class LocalEntryNotFoundError(Exception):
        pass

    def offline_load(name, accurate):
        raise LocalEntryNotFoundError("Cannot find the requested files in the local cache")

    monkeypatch.setattr(engines, "_build", offline_load)
    monkeypatch.setattr(engines, "availability", lambda name: (True, ""))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(engines.ModelNotDownloaded) as err:
        engines.build("whisper")
    assert err.value.engine == "whisper"
    seen = {}

    def online_load(name, accurate):
        import os
        seen["offline"] = os.environ["HF_HUB_OFFLINE"]
        return "engine"

    monkeypatch.setattr(engines, "_build", online_load)
    assert engines.build("whisper", allow_download=True) == "engine"
    import os
    assert seen["offline"] == "0" and os.environ["HF_HUB_OFFLINE"] == "1"     # offline again afterwards


def test_an_unusable_engine_is_an_error_with_the_reason(monkeypatch):
    monkeypatch.setattr(engines, "availability", lambda name: (False, "not installed: onnx_asr"))
    with pytest.raises(RuntimeError, match="not installed: onnx_asr"):
        engines.build("parakeet")


# ── settings and Options ────────────────────────────────────────────────────
def test_engine_setting_default_env_and_bad_values(tmp_path):
    import settings as st
    assert st.Settings().engine == "whisper"
    assert st.Settings(engine="bogus").clean().engine == "whisper"
    assert st.load(tmp_path / "none.json", env={"MYTRANSCRIBE_ENGINE": "medasr"}).engine == "medasr"


def test_options_lists_engines_and_disables_unavailable_ones(qapp, monkeypatch):
    import settings as st
    from options_dialog import OptionsDialog
    monkeypatch.setattr(engines, "availability",
                        lambda name, **k: (name in ("whisper", "parakeet"), "" if name != "medasr" else "no model"))
    d = OptionsDialog(st.Settings())
    names = [d.engine.itemData(i) for i in range(d.engine.count())]
    assert names == list(engines.ENGINES)
    assert d.engine.currentData() == "whisper" and d.accuracy.isEnabled()
    assert not d.engine.model().item(names.index("medasr")).isEnabled()
    assert "no model" in d.engine.itemText(names.index("medasr"))
    d.engine.setCurrentIndex(names.index("parakeet"))
    assert not d.accuracy.isEnabled()                       # Accuracy is a Whisper choice
    assert "CC BY 4.0" in d.engine_note.text() and "asked before any download" in d.engine_note.text()
    assert d.result_settings().engine == "parakeet"


def test_options_opens_the_log_in_its_own_window(qapp):
    import settings as st
    from options_dialog import OptionsDialog
    app_log.setup(to_file=False)
    logging.getLogger("test_engines").info("marker line 4711")
    d = OptionsDialog(st.Settings())
    d.show_log.click()
    assert d.log_window is not None and d.log_window.isVisible()
    assert d.log_window.isWindow()
    d.log_window.refresh()
    assert "marker line 4711" in d.log_window.view.toPlainText()
    d.log_window.close()


# ── logging without a console ───────────────────────────────────────────────
def test_setup_survives_having_no_console_and_keeps_recent_lines(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        app_log.setup(to_file=True, env={"LOCALAPPDATA": str(tmp_path)})
        print("libraries may still print")                   # must not raise
        logging.getLogger("x").info("to the file %d", 7)
        for h in root.handlers:
            h.flush()
        assert "to the file 7" in app_log.log_file({"LOCALAPPDATA": str(tmp_path)}).read_text(encoding="utf-8")
        assert "to the file 7" in app_log.memory().text()
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()


def test_memory_handler_is_bounded():
    h = app_log.MemoryHandler(capacity=3)
    h.setFormatter(logging.Formatter("%(message)s"))
    for i in range(10):
        h.emit(logging.LogRecord("n", logging.INFO, "", 0, f"line {i}", None, None))
    assert h.text() == "line 7\nline 8\nline 9" and h.count == 10


# ── the window: switching recogniser reloads it ─────────────────────────────
def test_changing_the_recogniser_in_options_reloads_the_engine(qapp, make_window):
    built = []

    def factory():
        built.append(FakeEngine())
        return built[-1]

    w = make_window(engine_factory=factory)
    assert len(built) == 1 and w.ready
    w.apply_settings(replace(w._settings, engine="parakeet"))
    assert not w.ready                                         # reloading: dictation is off for a moment
    assert wait_for(lambda: w.ready, app=qapp)
    assert len(built) == 2 and w._transcriber.engine is built[1]
    w.apply_settings(replace(w._settings, chime_volume=40))    # an unrelated change does not reload
    assert len(built) == 2 and w.ready


def test_a_model_that_is_not_downloaded_asks_first(qapp, make_window, monkeypatch):
    calls = []

    def factory():
        calls.append(w_holder[0]._allow_download if w_holder else False)
        if len(calls) == 1:
            raise engines.ModelNotDownloaded("whisper")
        return FakeEngine()

    w_holder = []
    import gui_med
    asked = []
    monkeypatch.setattr(gui_med.MedTranscriptionWindow, "_confirm_download",
                        lambda self, engine: asked.append(engine) or True)
    w = make_window(engine_factory=factory)                    # make_window waits for ready or an error
    w_holder.append(w)
    assert wait_for(lambda: w.ready, app=qapp)
    assert asked == ["whisper"] and len(calls) == 2


def test_declining_the_download_leaves_a_clear_message(qapp, make_window, monkeypatch):
    import gui_med
    monkeypatch.setattr(gui_med.MedTranscriptionWindow, "_confirm_download", lambda self, engine: False)

    def factory():
        raise engines.ModelNotDownloaded("parakeet")

    w = make_window(engine_factory=factory)
    assert wait_for(lambda: "not on this PC" in w._text_area.toPlainText(), app=qapp)
    assert not w.ready and "Show log" in w._text_area.toPlainText()
    time.sleep(0)

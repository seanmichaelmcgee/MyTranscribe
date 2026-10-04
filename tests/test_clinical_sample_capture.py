"""Fictional-test archive and GUI flow; no real microphone, clipboard or GPU."""
import json
from pathlib import Path
import sys
import wave

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import clinical_sample_capture as capture
from conftest import wait_for
from fakes import ArrayStream, FakeClipboard, FakeEngine, speech_like


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "local_result_path", lambda path: path)
    return capture.Archive(tmp_path, capture.ROOT / "docs" / "samples" / "personal_v1.json")


def test_stream_archives_exact_pcm_and_only_publishes_wav_on_close(tmp_path):
    frames = [b"\x01\x00" * 1024, b"\xfe\xff" * 512, b""]
    class Stream:
        def read(self, *args, **kwargs):
            return frames.pop(0)
        def stop_stream(self):
            pass
        def close(self):
            pass
    out = tmp_path / "sample.wav"
    stream = capture.CaptureStream(Stream(), out)
    first, second, last = stream.read(1024), stream.read(1024), stream.read(1024)
    assert not out.exists() and stream.partial.exists()
    stream.close()
    stream.close()  # framework cleanup can close twice
    with wave.open(str(out), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert wav.readframes(wav.getnframes()) == first + second
    assert last == b"" and stream.samples == 1536
    assert not stream.partial.exists()


def test_archive_preserves_reference_profile_and_unique_repeats(archive):
    assert not list(archive.out.glob("*.wav*"))  # constructing a recorder saves no idle audio
    sample = archive.rows[0]
    paths = []
    for _ in range(2):
        stream = archive.begin(ArrayStream(speech_like(1)), sample, "phone_remote_normal")
        stream.read(16000)
        stream.close()
        row = archive.finish("HGB normal.", ["HGB normal."], [], {"compute_type": "int8_float32"})
        paths.append(row["audio"])
        assert row["reference"] == sample["reference"]
        assert row["profile"] == "phone_remote_normal"
        assert row["reference_review_required"] is True
        diagnostic = json.loads((archive.out / row["audio"]).with_suffix(".app.json").read_text())
        assert diagnostic["formatted_text"] == "HGB normal."
        assert diagnostic["capture_adapter_sha256"]
    assert len(set(paths)) == 2 and len(archive.entries()) == 2


def test_incomplete_capture_cannot_publish_scored_manifest(archive):
    stream = archive.begin(ArrayStream(speech_like(1)), archive.rows[0], "local_normal")
    stream.read(16000)
    with pytest.raises(RuntimeError, match="complete test WAV"):
        archive.finish("text", [], [], {})
    assert not archive.manifest.exists()
    stream.close()


def test_combined_reference_includes_explicit_paragraph_commands(archive):
    sample = capture.combined_starters(archive.rows)
    assert sample["spoken"].count("New paragraph.") == 3
    assert sample["reference"].count("\n\n") == 3
    assert sample["category"] == "combined"
    assert "Romberg" in sample["terms"] and not sample["names"]


def test_changed_source_refuses_new_capture_without_publishing_audio(archive, monkeypatch):
    monkeypatch.setattr(capture, "source_hashes", lambda: {"changed": "source"})
    with pytest.raises(RuntimeError, match="restart the test window"):
        archive.begin(ArrayStream(speech_like(1)), archive.rows[0], "local_normal")
    assert not list(archive.out.glob("*.wav*"))


@pytest.mark.parametrize("single_script", [False, True])
def test_sample_gui_saves_recording_and_disables_selection_during_capture(qapp, archive, monkeypatch, single_script):
    import gui_qt
    from hw_profile import EngineConfig
    from settings import Settings
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    silent_chime = type("SilentChime", (), {"play_start": lambda self: None,
        "play_end": lambda self: None, "cleanup": lambda self: None})
    monkeypatch.setattr(gui_qt, "ChimePlayer", silent_chime)
    engine = FakeEngine()
    engine.config = EngineConfig("fake", "cpu", "float32", 2, "Test fixture")
    stream = ArrayStream(speech_like(1), pace_s=0.02)
    mic = type("Mic", (), {"session": lambda self: (stream, None)})()
    if single_script:
        archive.rows = archive.rows[:1]
    window = capture.window_class()(archive, mic, engine_factory=lambda: engine,
        include_combined=not single_script,
        base_prompt="Vocab.", text_pipeline=(None, None), install_hooks=False,
        settings=Settings(start_compact=False), settings_path=archive.out / "test_settings.json")
    clip = FakeClipboard()
    window._clipboard = lambda: clip
    window._clipboard_seq = clip.sequence
    try:
        assert wait_for(lambda: window.ready, app=qapp)
        assert window.sample_select.count() == (1 if single_script else 15)
        window.sample_select.setCurrentIndex(0 if single_script else 1)  # individual 00
        window.profile_select.setCurrentIndex(2)  # phone normal
        assert "H G B" in window.read_aloud.toPlainText()
        window._on_start_clicked()
        window._refresh_controls()
        assert not window.sample_select.isEnabled() and not window.profile_select.isEnabled()
        assert wait_for(lambda: archive.manifest.exists(), app=qapp)
        assert archive.entries()[0]["profile"] == "phone_remote_normal"
        assert archive.entries()[0]["scenario"] == "pc_v1_00"
        assert "saved locally" in window._status_text.text()
        window._refresh_controls()
        assert window.sample_select.isEnabled()
    finally:
        window.close()


def test_launcher_constructs_chime_owner_before_starting_microphone(archive, monkeypatch):
    from contextlib import nullcontext
    import gui_med
    import mic_ready
    import overnight_medasr
    import settings
    from PyQt6 import QtWidgets
    events = []

    class Mic:
        def start(self):
            assert "window_constructed" in events
            events.append("mic_started")
        def stop(self):
            events.append("mic_stopped")

    class Window:
        def __init__(self, *args, **kwargs):
            assert "mic_started" not in events
            assert kwargs["include_combined"] is False
            events.append("window_constructed")
        def show(self):
            events.append("shown")

    class App:
        def setStyleSheet(self, style):
            pass
        def exec(self):
            events.append("event_loop")

    monkeypatch.setattr(capture, "Archive", lambda *args: archive)
    monkeypatch.setattr(capture, "window_class", lambda: Window)
    monkeypatch.setattr(mic_ready, "ReadyMic", Mic)
    monkeypatch.setattr(gui_med, "register_cuda_dll_dirs", lambda: None)
    monkeypatch.setattr(settings, "load", lambda: settings.Settings())
    monkeypatch.setattr(overnight_medasr, "RunLock", lambda *args: nullcontext())
    monkeypatch.setattr(QtWidgets, "QApplication", lambda *args: App())
    monkeypatch.setattr(sys, "argv", ["capture", "--script", str(archive.out / "custom.json")])
    capture.main()
    assert events == ["window_constructed", "mic_started", "shown", "event_loop", "mic_stopped"]

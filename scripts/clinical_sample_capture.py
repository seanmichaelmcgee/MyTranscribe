"""Explicit fictional-test GUI. Reuses the production app; archives only started sessions.

The ordinary launcher never imports this adapter. No idle microphone audio is
saved. Recognition receives the production prompts, never the sample reference.
"""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import sys
import threading
import time
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from asr_trial_common import local_result_path, sha256, source_hashes, write_json
from record_snippets import load_samples


class CaptureStream:
    """Save exactly the PCM returned to transcription, with an incomplete-file marker."""
    def __init__(self, stream, path):
        self.stream, self.path = stream, Path(path)
        self.partial = self.path.with_suffix(".wav.partial")
        self.writer = wave.open(str(self.partial), "wb")
        self.writer.setnchannels(1)
        self.writer.setsampwidth(2)
        self.writer.setframerate(16000)
        self.lock = threading.Lock()
        self.closed = False
        self.samples = 0

    def read(self, n, exception_on_overflow=False):
        data = self.stream.read(n, exception_on_overflow=exception_on_overflow)
        with self.lock:
            if self.closed:
                raise OSError("Test capture is closed")
            if data:
                self.writer.writeframesraw(data)
                self.samples += len(data) // 2
        return data

    def stop_stream(self):
        self.stream.stop_stream()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.writer.close()
                self.partial.rename(self.path)
            finally:
                self.stream.close()


class Archive:
    """Attach fixed references and app diagnostics after a capture finishes."""
    def __init__(self, out, script):
        self.out = local_result_path(Path(out))
        self.out.mkdir(parents=True, exist_ok=True)
        self.script_hash = sha256(script)
        self.rows = load_samples(script)
        self.launch_sources = source_hashes()
        self.adapter_hash = sha256(Path(__file__))
        self.manifest = self.out / "manifest.json"
        old = self.entries()
        if any(row.get("sample_script_sha256") != self.script_hash for row in old):
            raise ValueError("Choose a fresh folder for a different sample packet")
        self.active = None

    def entries(self):
        return json.loads(self.manifest.read_text(encoding="utf-8")) if self.manifest.exists() else []

    def begin(self, stream, sample, profile):
        if self.active is not None:
            raise RuntimeError("Previous test capture has not finished")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", profile):
            raise ValueError("Invalid capture profile")
        if source_hashes() != self.launch_sources or sha256(Path(__file__)) != self.adapter_hash:
            raise RuntimeError("App source changed; restart the test window before recording")
        path = self.out / (sample["scenario"] + "__" + profile + "__" + uuid.uuid4().hex + ".wav")
        capture = CaptureStream(stream, path)
        self.active = dict(capture=capture, sample=dict(sample), profile=profile,
                           source_sha256=self.launch_sources, started=time.time())
        return capture

    def finish(self, text, processed_chunks, chunk_stats, engine_config, capture_error=None):
        active = self.active
        if active is None:
            raise RuntimeError("No test capture to finalize")
        capture = active["capture"]
        if not capture.closed or not capture.path.exists() or capture.samples == 0:
            raise RuntimeError("No complete test WAV was saved")
        sample = active["sample"]
        row = dict(sample, audio=capture.path.name, profile=active["profile"],
                   seconds=capture.samples / 16000, sample_script_sha256=self.script_hash,
                   reference_review_required=True, capture_error=capture_error)
        diagnostic = dict(audio=row["audio"], source_sha256=active["source_sha256"],
                          capture_adapter_sha256=self.adapter_hash,
                          source_unchanged=(source_hashes() == self.launch_sources and
                                            sha256(Path(__file__)) == self.adapter_hash),
                          model_config=engine_config, processed_chunks=processed_chunks,
                          formatted_text=text, chunk_stats=chunk_stats,
                          started=active["started"], finished=time.time(),
                          note="Confirm the spoken reference before scoring; app chunks are postprocessed.")
        write_json(capture.path.with_suffix(".app.json"), diagnostic)
        write_json(self.manifest, self.entries() + [row])
        self.active = None
        return row


def combined_starters(rows):
    chosen = [rows[i] for i in (0, 3, 6, 7)]
    return dict(scenario="pc_v1_combined_starters", category="combined", split="calibration",
                spoken=" New paragraph. ".join(row["spoken"] for row in chosen),
                reference="\n\n".join(row["reference"] for row in chosen),
                terms=list(dict.fromkeys(term for row in chosen for term in row["terms"])), names=[])


def window_class():
    """Import the GUI only for an explicit test launch or a headless GUI test."""
    from PyQt6.QtWidgets import QComboBox, QLabel, QTextEdit
    from gui_med import MedTranscriptionWindow

    class SampleWindow(MedTranscriptionWindow):
        def __init__(self, archive, mic, include_combined=True, **kwargs):
            self.archive, self.sample_mic = archive, mic
            self.samples = ([combined_starters(archive.rows)] if include_combined else []) + archive.rows
            super().__init__(stream_factory=self._test_stream, autopaste=False, **kwargs)
            self.setWindowTitle("MyTranscribe — FICTIONAL TEST CAPTURE")
            layout = self.centralWidget().layout()
            badge = QLabel("TEST MODE: each dictation saves local audio and text. Fictional cases only.")
            badge.setWordWrap(True)
            layout.insertWidget(0, badge)
            self.sample_select = QComboBox()
            if include_combined:
                self.sample_select.addItem("Combined starters — read New paragraph between examples")
            for i, row in enumerate(archive.rows):
                self.sample_select.addItem(f"{i:02d} — {row.get('label', row['category'])}")
            layout.insertWidget(1, self.sample_select)
            self.profile_select = QComboBox()
            for label, value in (("Local normal", "local_normal"), ("Local whisper", "local_whisper"),
                                 ("Phone normal", "phone_remote_normal"), ("Phone whisper", "phone_remote_whisper"),
                                 ("Local fast / mumbled", "local_fast")):
                self.profile_select.addItem(label, value)
            layout.insertWidget(2, self.profile_select)
            self.read_aloud = QTextEdit()
            self.read_aloud.setReadOnly(True)
            self.read_aloud.setMinimumHeight(115)
            self.read_aloud.setMaximumHeight(210)
            layout.insertWidget(3, self.read_aloud)
            self.sample_select.currentIndexChanged.connect(self._show_sample)
            self._compact_btn.setEnabled(False)
            self._show_sample()
            self.resize(580, 570)

        def _show_sample(self, *args):
            sample = self.samples[self.sample_select.currentIndex()]
            self.read_aloud.setPlainText(sample["spoken"])
            hint = {"clear": "local_normal", "normal": "local_normal",
                    "fast_mumbled": "local_fast"}.get(sample.get("intended_delivery"))
            if hint:
                self.profile_select.setCurrentIndex(self.profile_select.findData(hint))

        def _test_stream(self):
            sample = self.samples[self.sample_select.currentIndex()]
            stream, owner = self.sample_mic.session()
            try:
                return self.archive.begin(stream, sample, self.profile_select.currentData()), owner
            except Exception:
                stream.close()
                raise

        def _refresh_controls(self):
            super()._refresh_controls()
            if hasattr(self, "sample_select"):
                allowed = self._can_start()
                self.sample_select.setEnabled(allowed)
                self.profile_select.setEnabled(allowed)

        def _finalize(self, text, from_hotkey):
            super()._finalize(text, from_hotkey)
            try:
                self.archive.finish(text, list(self._transcriber.transcriptions),
                                    [asdict(stat) for stat in self._transcriber.chunk_stats],
                                    asdict(self._engine.config), self._transcriber.capture_error)
            except Exception:
                self._set_status("Test save failed — keep this window open", "warn")
                return
            self._set_status("Test saved locally — choose the next sample or repeat", "idle")

    return SampleWindow


def main():
    import os
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from gui_med import MED_QSS, register_cuda_dll_dirs
    from mic_ready import ReadyMic
    import settings
    from overnight_medasr import RunLock
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results_1060" / "personal_v1_capture")
    default_script = ROOT / "docs" / "samples" / "personal_v1.json"
    parser.add_argument("--script", type=Path, default=default_script,
                        help="Frozen fictional read-aloud packet; used for capture/scoring only")
    args = parser.parse_args()
    archive = Archive(args.out, args.script)
    register_cuda_dll_dirs()
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(MED_QSS)
    mic = ReadyMic()
    try:
        with RunLock(ROOT / "results_medasr" / ".overnight.lock"):
            options = replace(settings.load(), start_compact=False, live_insert=False)
            window = window_class()(archive, mic, settings=options,
                                    include_combined=args.script.resolve() == default_script.resolve(),
                                    settings_path=archive.out / "test_ui_settings.json")
            # Construct the chime's PortAudio owner before opening the microphone.
            # Concurrent PyAudio initialization can crash natively on Windows.
            mic.start()
            window.show()
            app.exec()
    except RuntimeError as exc:
        QMessageBox.warning(None, "Test capture could not start", str(exc))
    finally:
        mic.stop()


if __name__ == "__main__":
    main()

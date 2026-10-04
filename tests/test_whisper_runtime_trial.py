"""Runtime changes must keep production decoding and truthful experiment labels."""
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import whisper_runtime_trial as trial


@pytest.mark.parametrize("mode,expected", [("default", (0.0, 0.2)), ("zero", 0.0)])
def test_decoder_keeps_audio_prompt_and_collects_lazy_diagnostics(mode, expected):
    calls = []
    def transcribe(audio, temperature=(0.0, 0.2), **kwargs):
        calls.append((audio, temperature, kwargs))
        return iter([SimpleNamespace(text="example", temperature=0.0, avg_logprob=-0.2,
                                    compression_ratio=1.1, no_speech_prob=0.01)]), "info"
    engine = SimpleNamespace(beam_size=3, model=SimpleNamespace(transcribe=transcribe))
    traces, temperatures = trial.configure_decoder(engine, 2.0, mode)
    audio = np.zeros(16000, dtype=np.float32)
    segments, info = engine.model.transcribe(audio, beam_size=3, patience=1.0,
                                           initial_prompt="Medical terms", language="en")
    assert not traces[0].get("completed")
    assert [s.text for s in segments] == ["example"] and info == "info"
    assert calls[0][0] is audio
    assert calls[0][1] == temperatures == expected
    assert calls[0][2]["initial_prompt"] == "Medical terms"
    assert calls[0][2]["patience"] == 2.0 and calls[0][2]["language"] == "en"
    assert "initial_prompt" not in traces[0]["parameters"]
    assert traces[0]["completed"] and traces[0]["segments"][0]["avg_logprob"] == -0.2


def test_failed_trial_restores_patches(monkeypatch, tmp_path):
    engine = trial.fw_engine.FasterWhisperEngine
    writer = trial.trial_chunk_window.trial_asr.write_json
    monkeypatch.setattr(trial, "local_result_path", lambda p: p)
    monkeypatch.setattr(trial, "model_integrity", lambda p: {"path": str(p), "sha256": {}})
    monkeypatch.setattr(trial.trial_chunk_window, "main", lambda argv: (_ for _ in ()).throw(RuntimeError("failed")))
    with pytest.raises(RuntimeError, match="failed"):
        trial.main(["--model", str(tmp_path), "--out", str(tmp_path / "run.json")])
    assert trial.fw_engine.FasterWhisperEngine is engine
    assert trial.trial_chunk_window.trial_asr.write_json is writer


def test_source_change_cannot_publish_completed_record(monkeypatch, tmp_path):
    monkeypatch.setattr(trial, "local_result_path", lambda p: p)
    monkeypatch.setattr(trial, "model_integrity", lambda p: {"path": str(p), "sha256": {}})
    snapshots = iter([{"src": "a"}, {"src": "b"}])
    monkeypatch.setattr(trial, "source_hashes", lambda: next(snapshots))
    writes = []
    monkeypatch.setattr(trial.trial_chunk_window.trial_asr, "write_json", lambda *args: writes.append(args))
    def run(argv):
        trial.trial_chunk_window.trial_asr.write_json("unused", {"completed": True, "config": {}})
    monkeypatch.setattr(trial.trial_chunk_window, "main", run)
    with pytest.raises(ValueError, match="Source changed"):
        trial.main(["--model", str(tmp_path), "--out", str(tmp_path / "run.json")])
    assert not writes

"""Window override provenance and restoration; no model or audio needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import chunked_transcriber
import trial_chunk_window as trial


@pytest.mark.parametrize("seconds", [20, 30])
def test_override_and_checkpoint_provenance(monkeypatch, seconds):
    constructed, checkpoints = [], []
    def original(*args, **kwargs):
        constructed.append(kwargs)
    monkeypatch.setattr(chunked_transcriber, "ChunkedTranscriber", original)
    monkeypatch.setattr(trial.trial_asr, "write_json", lambda path, value: checkpoints.append(value))
    prior_write = trial.trial_asr.write_json
    def fake_main(argv):
        chunked_transcriber.ChunkedTranscriber(chunk_target_s=20)
        trial.trial_asr.write_json("unused", dict(config={}, completed=True))
        return 0
    monkeypatch.setattr(trial.trial_asr, "main", fake_main)
    assert trial.main(["--chunk-seconds", str(seconds)]) == 0
    assert constructed[0]["chunk_target_s"] == seconds
    assert checkpoints[0]["chunk_target_s"] == seconds
    assert checkpoints[0]["config"]["chunk_override_source_sha256"]
    assert chunked_transcriber.ChunkedTranscriber is original
    assert trial.trial_asr.write_json is prior_write


def test_restores_originals_on_failure(monkeypatch):
    prior = chunked_transcriber.ChunkedTranscriber
    writer = trial.trial_asr.write_json
    def failed(argv):
        raise RuntimeError("trial failure")
    monkeypatch.setattr(trial.trial_asr, "main", failed)
    with pytest.raises(RuntimeError):
        trial.main([])
    assert chunked_transcriber.ChunkedTranscriber is prior
    assert trial.trial_asr.write_json is writer


def test_source_change_cannot_publish_success(monkeypatch):
    hashes = iter([{"fixed": "before"}, {"fixed": "after"}])
    monkeypatch.setattr(trial, "source_hashes", lambda: next(hashes))
    published = []
    monkeypatch.setattr(trial.trial_asr, "write_json", lambda *args: published.append(args))
    def fake_main(argv):
        trial.trial_asr.write_json("unused", dict(config={}, completed=True))
    monkeypatch.setattr(trial.trial_asr, "main", fake_main)
    with pytest.raises(ValueError, match="Source changed"):
        trial.main([])
    assert not published

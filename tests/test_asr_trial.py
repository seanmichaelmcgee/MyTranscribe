"""Guard the trial's privacy/provenance and raw-vs-formatted scoring boundaries."""
import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import asr_trial_common as common
import score_asr_trial as scorer
from trial_asr import ReplayStream


def corpus(tmp_path, monkeypatch):
    frozen_sources = common.source_hashes()
    monkeypatch.setattr(scorer, "source_hashes", lambda: frozen_sources)
    monkeypatch.setattr(common, "ROOT", tmp_path)
    audio = tmp_path / "clip.wav"
    with wave.open(str(audio), "wb") as w:
        w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        w.writeframes(b"\x01\x00" * 160)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([dict(audio="clip.wav", reference="Renal normal.\nReview.",
        spoken="Renal normal. New line. Review.", category="result", terms=["renal"], names=[])]))
    return manifest


def make_run(entries, digest):
    e = entries[0]
    return dict(schema=1, completed=True, corpus_sha256=digest, source_sha256=scorer.source_hashes(),
                repeats=1, versions={"wordfreq":"3.1.1"}, utterances=[dict(clip_id=e["clip_id"],
                audio_sha256=e["audio_sha256"], repeat=0, raw=e["spoken"], cleaned=e["reference"])])


def test_freeze_reference_and_audio(tmp_path, monkeypatch):
    manifest=corpus(tmp_path, monkeypatch)
    entries, digest=common.load_corpus([manifest])
    run=make_run(entries, digest)
    scorer.validate_run(run, entries, digest)
    rows=json.loads(manifest.read_text()); rows[0]["reference"]="Renal abnormal."
    manifest.write_text(json.dumps(rows))
    changed, new_digest=common.load_corpus([manifest])
    assert new_digest != digest
    with pytest.raises(ValueError, match="Corpus"):
        scorer.validate_run(run, changed, new_digest)
    entries[0]["_path"].write_bytes(b"bad audio")
    with pytest.raises((wave.Error, EOFError)):
        common.load_corpus([manifest])


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "unfinished", "audio", "source"])
def test_reject_incomplete_or_mismatched_run(tmp_path, monkeypatch, mutation):
    entries, digest=common.load_corpus([corpus(tmp_path, monkeypatch)])
    run=make_run(entries,digest)
    if mutation=="duplicate": run["utterances"] *= 2
    if mutation=="missing": run["utterances"]=[]
    if mutation=="unfinished": run["completed"]=False
    if mutation=="audio": run["utterances"][0]["audio_sha256"]="bad"
    if mutation=="source": run["source_sha256"]={}
    with pytest.raises(ValueError): scorer.validate_run(run,entries,digest)


def test_raw_compared_to_spoken_and_cleaned_to_written(tmp_path, monkeypatch):
    entries,digest=common.load_corpus([corpus(tmp_path,monkeypatch)])
    result=scorer.score_run(make_run(entries,digest),entries)
    assert result["raw"]["summary"]["ALL"]["wer"]==0
    assert result["cleaned"]["summary"]["ALL"]["wer"]==0
    assert result["raw"]["reference"]=="spoken"
    assert result["cleaned"]["reference"]=="written"


def test_model_integrity_rejects_tampering_and_executable(tmp_path):
    for name in common.MODEL_FILES: (tmp_path/name).write_bytes(name.encode())
    common.write_json(tmp_path/"integrity.json",dict(model_id=common.MODEL_ID,
        revision=common.MODEL_REVISION,sha256={n:common.sha256(tmp_path/n) for n in common.MODEL_FILES}))
    common.verify_model(tmp_path)
    (tmp_path/"model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError,match="mismatch"): common.verify_model(tmp_path)
    (tmp_path/"model.safetensors").write_bytes(b"model.safetensors")
    (tmp_path/"modeling_custom.py").write_text("raise RuntimeError('never run')")
    with pytest.raises(ValueError,match="Unexpected"): common.verify_model(tmp_path)


def test_path_traversal_and_duplicates(tmp_path,monkeypatch):
    manifest=corpus(tmp_path,monkeypatch)
    rows=json.loads(manifest.read_text()); rows *= 2
    manifest.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match="Duplicate"): common.load_corpus([manifest])
    rows[0]["audio"]="../outside.wav"; manifest.write_text(json.dumps(rows[:1]))
    with pytest.raises(ValueError): common.load_corpus([manifest])


def test_missing_latency_is_not_zero():
    assert scorer.distribution([None,None])==dict(n=0,mean=None,p50=None,p95=None,maximum=None)
    assert scorer.distribution([1,2,3])["p95"]==3


def test_numbered_items_and_review_signals():
    assert scorer.format_counts("1. A\n2. B", "1. A\n3. B")
    assert scorer.number_items("1. A\n2. B") != scorer.number_items("1. A\n3. B")
    assert scorer.risk_tokens("No pain, 10 mg") != scorer.risk_tokens("Pain, 100 mg")


def test_replay_returns_exact_pcm_without_microphone():
    stream=ReplayStream(b"\x01\x00"*5)
    assert len(stream.read(3))==6
    assert len(stream.read(3))==4
    assert stream.read(3)==b""
    assert stream.finished is not None

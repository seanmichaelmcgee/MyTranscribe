"""Capture preparation and resume behavior without opening a microphone."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import asr_trial_common
import record_snippets
from record_snippets import ROOT, SNIPPETS, load_samples, select_samples


def test_personal_packet_has_frozen_references_and_separate_holdout():
    rows = load_samples(ROOT / "docs" / "samples" / "personal_v1.json")
    assert len(rows) == 14
    assert {r["category"] for r in rows} == {"message", "result", "exam", "letter"}
    assert [i for i, r in enumerate(rows) if r["split"] == "holdout"] == [9, 12, 13]
    assert all(r["reference"] and r["terms"] for r in rows)
    assert "Romberg" in rows[6]["terms"] and "Romberg" not in rows[6]["names"]


@pytest.mark.parametrize("mutation", ["duplicate", "path", "reference", "terms", "split"])
def test_bad_sample_data_is_rejected_before_capture(tmp_path, mutation):
    rows = load_samples(ROOT / "docs" / "samples" / "personal_v1.json")[:2]
    if mutation == "duplicate":
        rows[1]["scenario"] = rows[0]["scenario"]
    elif mutation == "path":
        rows[0]["scenario"] = "../escape"
    elif mutation == "reference":
        del rows[0]["reference"]
    elif mutation == "terms":
        rows[0]["terms"] = "not a term list"
    else:
        rows[0]["split"] = "unknown"
    path = tmp_path / "samples.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError):
        load_samples(path)


def test_custom_resume_requires_both_manifest_and_audio_and_redo_is_explicit(tmp_path):
    rows = load_samples(ROOT / "docs" / "samples" / "personal_v1.json")[:3]
    manifest = [{"audio": "pc_v1_00__phone_normal.wav"}, {"audio": "pc_v1_01__phone_normal.wav"}]
    (tmp_path / manifest[0]["audio"]).touch()
    pending = select_samples(rows, manifest, tmp_path, "phone_normal", resume=True)
    assert [i for i, _ in pending] == [1, 2]  # missing WAV is offered again
    redo = select_samples(rows, manifest, tmp_path, "phone_normal", redo={0}, resume=True)
    assert [i for i, _ in redo] == [0]
    other_profile = select_samples(rows, manifest, tmp_path, "headset_normal", resume=True)
    assert [i for i, _ in other_profile] == [0, 1, 2]


def test_legacy_samples_keep_indices_filenames_and_category_filters(tmp_path):
    rows = load_samples()
    assert len(rows) == len(SNIPPETS)
    assert rows[0]["scenario"] == "00_message"
    assert rows[27]["scenario"] == "27_letter"
    selected = select_samples(rows, [], tmp_path, "real", keep={"letter"}, redo={27})
    assert [i for i, _ in selected] == [27]


def test_recorder_writes_scoreable_audio_and_frozen_metadata_without_a_real_mic(tmp_path, monkeypatch):
    row = load_samples(ROOT / "docs" / "samples" / "personal_v1.json")[13]
    script = tmp_path / "samples.json"
    script.write_text(json.dumps([row]), encoding="utf-8")
    out = tmp_path / "results_voice"
    lifecycle = []

    class FakePA:
        def terminate(self):
            lifecycle.append("terminate")

    class FakeMic:
        def __init__(self, **kwargs):
            pass
        def start(self):
            lifecycle.append("start")
        def stop(self):
            lifecycle.append("stop")

    monkeypatch.setitem(sys.modules, "pyaudio", SimpleNamespace(PyAudio=FakePA, paInt16=8))
    monkeypatch.setitem(sys.modules, "mic_ready", SimpleNamespace(ReadyMic=FakeMic))
    monkeypatch.setattr(record_snippets, "record_until_enter", lambda mic: b"\x01\x00" * 16000)
    monkeypatch.setattr(record_snippets, "local_result_path", lambda path: path)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(asr_trial_common, "ROOT", tmp_path)
    assert record_snippets.main(["--script", str(script), "--out", str(out), "--profile", "phone_normal"]) == 0
    entries, _ = asr_trial_common.load_corpus([out / "manifest.json"])
    assert len(entries) == 1 and entries[0]["duration_s"] == 1
    assert entries[0]["scenario"] == row["scenario"]
    assert entries[0]["reference"] == row["reference"]
    assert entries[0]["split"] == "holdout"
    assert entries[0]["sample_script_sha256"] == asr_trial_common.sha256(script)
    assert entries[0]["profile"] == "phone_normal"
    assert lifecycle == ["start", "stop", "terminate"]

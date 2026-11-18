"""synth_voices: the voice panel, what each voice is asked to say, and making clips (no network)."""

import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import synth_voices as sv  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test here may reach the API, whatever stand-ins it uses."""
    def refuse(*_args, **_kwargs):
        raise AssertionError("a test tried to reach the network")
    monkeypatch.setattr(sv.urllib.request, "urlopen", refuse)


def test_panel_is_balanced_and_holds_two_voices_back():
    panel = sv.load_panel()
    voices = panel["voices"]
    assert len(voices) == 12 and len({v["voice"] for v in voices}) == 12
    assert sorted(v["sex"] for v in voices).count("F") == 6
    assert [v["id"] for v in voices if v["split"] == "held"] == ["V06", "V12"]
    assert {v["stop"] for v in voices} == {"period", "full stop"}


def test_units_minus_signs_and_pauses_are_spelled_out_for_the_voice():
    said = "Take 500 mg comma 1 g and 200 mcg period Hb 104 g/L comma 6 to 8 mmol/L comma 2.1 L and -3.1 period"
    assert sv.voice_text(said) == ("Take 500 milligrams comma, 1 gram and 200 micrograms period. Hb 104 grams per "
                                   "litre comma, 6 to 8 millimoles per litre comma, 2.1 litres and minus 3.1 period.")
    assert sv.voice_text("heavy periods, no comma here.", mode="natural") == "heavy periods, no comma here."


def test_plan_covers_every_voice_and_script_with_its_own_stop_word():
    clips = sv.plan(sv.load_panel())
    assert len(clips) == 12 * 40
    assert all(len(c["input"]) <= sv.MAX_INPUT for c in clips)
    v04 = next(c for c in clips if c["voice_id"] == "V04" and c["item"] == "e05")
    v01 = next(c for c in clips if c["voice_id"] == "V01" and c["item"] == "e05")
    assert "full stop." in v04["input"] and "period" not in v04["input"]
    assert "period." in v01["input"] and "Nigerian" in v04["instructions"]
    natural = next(c for c in clips if c["item"] == "n02")
    assert " um " in natural["input"] and "new paragraph" not in natural["input"]


def test_make_refuses_without_go_and_never_reads_the_key(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "read_key", lambda *_: pytest.fail("key read without --go"))
    with pytest.raises(SystemExit, match="--go"):
        sv.main(["make", "--out", str(tmp_path), "--voices", "V01", "--items", "e07"])


def test_make_writes_clips_and_manifest_and_skips_what_is_done(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "read_key", lambda *_: "test-key")
    sent = []
    tone = (np.sin(2 * np.pi * 440 * np.arange(sv.SOURCE_RATE) / sv.SOURCE_RATE) * 8000).astype("<i2").tobytes()

    def fake_post(body, key):
        sent.append((body, key))
        return tone

    args = ["make", "--go", "--out", str(tmp_path), "--voices", "V01,V07", "--items", "e07,q01", "--workers", "1"]
    monkeypatch.setattr(sv, "_post", fake_post)
    sv.main(args)
    assert len(sent) == 4 and all(k == "test-key" and b["response_format"] == "pcm" for b, k in sent)
    rows = [json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4 and all(r["ai_generated"] and r["terms_read"] == "2026-11-18" for r in rows)
    assert "test-key" not in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8")
    with wave.open(str(tmp_path / "V01" / "e07.wav")) as w:
        assert (w.getframerate(), w.getnframes()) == (16000, 16000)
    assert "never for training" in (tmp_path / "README.txt").read_text(encoding="utf-8")
    sv.main(args)                                    # everything made already: nothing sent
    assert len(sent) == 4


def test_budget_stops_a_run_before_it_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "read_key", lambda *_: pytest.fail("key read over budget"))
    with pytest.raises(SystemExit, match="budget"):
        sv.main(["make", "--go", "--out", str(tmp_path), "--budget-usd", "0.01"])


def test_fidelity_forgives_formatting_but_flags_a_skipped_sign_off():
    clip = next(c for c in sv.plan(sv.load_panel(), ["V01"], ["n02"]))
    heard = clip["required"].replace("15 milligrams", "15mg").replace("6 weeks", "six weeks")
    assert sv.judge(clip, heard) == []
    skipped = heard.split("Yours sincerely")[0]
    gaps = sv.judge(clip, skipped)
    assert len(gaps) == 1 and "priya raman" in gaps[0][0]


def test_a_self_correction_the_recogniser_tidied_away_is_not_the_voices_fault():
    clip = next(c for c in sv.plan(sv.load_panel(), ["V04"], ["n02"]))
    assert "sorry" in clip["input"] and "sorry" not in clip["required"]
    assert sv.judge(clip, clip["required"]) == [] and sv.judge(clip, clip["input"]) == []


def test_check_then_reject_sets_a_flagged_clip_aside_for_remaking(tmp_path):
    clips = {c["item"]: c for c in sv.plan(sv.load_panel(), ["V01"], ["e07", "n02"])}
    rows = []
    for item, sha in (("e07", "a" * 64), ("n02", "b" * 64)):
        sv.write_wav(tmp_path / "V01" / f"{item}.wav", np.zeros(1600), sv.RATE)
        sv.write_wav(tmp_path / "V01" / f"{item}.24k.wav", np.zeros(2400), sv.SOURCE_RATE)
        rows.append({"voice_id": "V01", "item": item, "wav": f"V01/{item}.wav", "sha256": sha})
    (tmp_path / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    heard = {"e07.wav": clips["e07"]["input"], "n02.wav": clips["n02"]["required"].split("Yours")[0]}
    args = sv.argparse.Namespace(out=tmp_path, voices=["V01"], items=["e07", "n02"], model=None)
    sv.cmd_check(args, sv.load_panel(), transcribe=lambda p: heard[p.name])
    sv.cmd_reject(args, sv.load_panel())
    assert sv.done_clips(tmp_path) == {("V01", "e07")}
    assert not (tmp_path / "V01" / "n02.wav").exists()
    assert len(list((tmp_path / "_rejected").glob("*.wav"))) == 2
    assert json.loads((tmp_path / "rejected.jsonl").read_text(encoding="utf-8"))["item"] == "n02"


def test_resampling_keeps_length_and_pitch():
    t = np.arange(sv.SOURCE_RATE) / sv.SOURCE_RATE
    out = sv.resample(np.sin(2 * np.pi * 1000 * t))
    assert len(out) == sv.RATE
    peak = np.argmax(np.abs(np.fft.rfft(out))) * sv.RATE / len(out)
    assert abs(peak - 1000) < 2


@pytest.mark.skipif(sys.platform != "win32", reason="Windows account encryption")
def test_reads_a_key_saved_the_powershell_way(tmp_path):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    data = "sk-test-not-real".encode("utf-16-le")
    buf = ctypes.create_string_buffer(data, len(data))
    src, out = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), Blob()
    assert ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out))
    hexed = ctypes.string_at(out.pbData, out.cbData).hex()
    ctypes.windll.kernel32.LocalFree(out.pbData)
    key_file = tmp_path / "openai.dpapi"
    key_file.write_text("﻿" + hexed, encoding="utf-8")       # PowerShell writes a byte-order mark
    assert sv.read_key(key_file) == "sk-test-not-real"

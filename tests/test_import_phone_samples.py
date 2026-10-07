"""Phone import uses existing codecs, preserves originals and publishes honest corpus data."""
from pathlib import Path
import sys
import wave

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import asr_trial_common
import import_phone_samples as phone


def pcm_file(path, samples, rate=16000):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.astype("<i2").tobytes())


def test_pcm_round_trip_preserves_every_sample(tmp_path):
    samples = np.tile(np.array([-32768, -100, 0, 100, 32767], dtype=np.int16), 3200)
    source, out = tmp_path / "input.wav", tmp_path / "output.wav.partial"
    pcm_file(source, samples)
    metadata = phone.decode_to_wav(source, out)
    with wave.open(str(out), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert wav.readframes(wav.getnframes()) == samples.astype("<i2").tobytes()
    assert metadata["seconds"] == 1
    assert metadata["output_peak"] == 1 and metadata["clipping_fraction"] == 0.4


def test_m4a_aac_from_phone_rate_is_decoded_locally(tmp_path):
    import av
    source = tmp_path / "voice.m4a"
    samples = (0.2 * np.sin(2 * np.pi * 440 * np.arange(48000) / 48000)).astype(np.float32)
    with av.open(str(source), mode="w", format="mp4") as container:
        stream = container.add_stream("aac", rate=48000)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="fltp", layout="mono")
        frame.sample_rate = 48000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    result = phone.decode_to_wav(source, tmp_path / "normalized.wav.partial")
    assert result["source_audio"]["codec"] == "aac"
    assert result["source_audio"]["sample_rate"] == 48000
    assert 0.98 <= result["seconds"] <= 1.04
    assert 0.1 < result["output_rms"] < 0.2


def test_playlist_disguised_as_audio_is_rejected(tmp_path, monkeypatch):
    import av
    calls = []
    original_deny = phone.deny_external_io
    def deny(*args):
        calls.append(args)
        return original_deny(*args)
    monkeypatch.setattr(phone, "deny_external_io", deny)
    source = tmp_path / "playlist.m4a"
    source.write_text("#EXTM3U\n#EXTINF:1,\nhttp://127.0.0.1:1/forbidden.wav\n", encoding="utf-8")
    with pytest.raises(av.error.FFmpegError):
        phone.decode_to_wav(source, tmp_path / "out.wav.partial")
    assert calls == []  # rejected before any external-media open attempt
    assert not (tmp_path / "out.wav.partial").exists()
    with pytest.raises(OSError, match="External media"):
        phone.deny_external_io("file:///arbitrary", 0, {})


def test_decode_duration_is_bounded(tmp_path):
    source = tmp_path / "long.wav"
    pcm_file(source, np.zeros(16000, dtype=np.int16))
    with pytest.raises(ValueError, match="duration limit"):
        phone.decode_to_wav(source, tmp_path / "partial.wav", max_seconds=0.01)


def test_import_preserves_original_and_reference_and_distinct_repeats(tmp_path, monkeypatch):
    monkeypatch.setattr(phone, "local_result_path", lambda path: path)
    monkeypatch.setattr(asr_trial_common, "ROOT", tmp_path)
    source, out = tmp_path / "input.wav", tmp_path / "results_phone"
    pcm_file(source, np.ones(16000, dtype=np.int16))
    first = phone.import_recording(source, out, [6], voice="whisper", decoder=phone.decode_to_wav)
    second = phone.import_recording(source, out, [6], voice="whisper", decoder=phone.decode_to_wav)
    assert first["audio"] != second["audio"]
    assert first["profile"] == "phone_file_whisper"
    assert first["reference_review_required"] and "Romberg" in first["terms"]
    assert (out / first["original_audio"]).read_bytes() == source.read_bytes()
    entries, _ = asr_trial_common.load_corpus([out / "manifest.json"])
    assert len(entries) == 2 and all(row["duration_s"] == 1 for row in entries)


def test_failed_import_does_not_publish_or_leave_owned_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(phone, "local_result_path", lambda path: path)
    source, out = tmp_path / "input.wav", tmp_path / "results_phone"
    pcm_file(source, np.ones(100, dtype=np.int16))
    def failed_decoder(source, path):
        path.write_bytes(b"incomplete")
        raise ValueError("Simulated decode failure")
    with pytest.raises(ValueError, match="Simulated decode failure"):
        phone.import_recording(source, out, [0], decoder=failed_decoder)
    assert not (out / "manifest.json").exists()
    assert not list(out.glob("*.partial"))


def test_combining_validation_samples_retains_holdout_status():
    sample = phone.sample_reference([0, 9])
    assert sample["split"] == "holdout" and sample["category"] == "combined"
    assert "New paragraph." in sample["spoken"]
    assert "\n\n" in sample["reference"]

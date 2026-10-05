"""Runtime changes must keep production decoding and truthful experiment labels."""
from pathlib import Path
import sys
from types import SimpleNamespace
import hashlib
import json

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import whisper_runtime_trial as trial
import whisper_decoder_trace as metadata


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


def fake_decoder(trace=None, *, error=None):
    """Keep the raw generator alive so close/throw delegation is observable."""
    events, calls, originals = [], [], []
    segments = [SimpleNamespace(text="first", tokens=[101, 202], temperature=0.4,
        avg_logprob=-0.2, compression_ratio=1.1, no_speech_prob=0.01),
        SimpleNamespace(text="second", tokens=[303], temperature=0.4)]
    info = SimpleNamespace(duration=2.0, duration_after_vad=1.25,
        transcription_options=SimpleNamespace(beam_size=5, max_new_tokens=24,
            initial_prompt="private-info-prompt", prefix="private-prefix", hotwords="private-hotwords"),
        vad_options=SimpleNamespace(threshold=0.5, speech_pad_ms=400))
    def transcribe(audio, temperature=(0.0, 0.2), **kwargs):
        calls.append((audio, temperature, kwargs))
        def generate():
            try:
                events.append("first")
                sent = yield segments[0]
                events.append(("sent", sent))
                if error is not None:
                    raise error
                events.append("second")
                yield segments[1]
            finally:
                events.append("raw-closed")
        source = generate()
        originals.append(source)
        return source, info
    engine = SimpleNamespace(beam_size=5, model=SimpleNamespace(transcribe=transcribe))
    legacy, _ = trial.configure_decoder(engine, 2.0, "default", trace=trace)
    audio = np.array([0.125, -0.25], dtype=np.float32)
    iterator, returned_info = engine.model.transcribe(audio, initial_prompt="private-actual-prompt",
        max_new_tokens=24, temperature=0.4, prefix="private-prefix", hotwords="private-hotwords",
        suppress_tokens=[707, 808], condition_on_previous_text=False)
    assert returned_info is info and calls[0][0] is audio and not events
    return iterator, segments, events, calls, originals, legacy, audio


def test_trace_preserves_calls_objects_laziness_and_send_behavior():
    observations = []
    for enabled in (False, True):
        trace = metadata.DecoderTrace() if enabled else None
        iterator, segments, events, calls, _, legacy, _ = fake_decoder(trace)
        assert next(iterator) is segments[0] and events == ["first"]
        # Existing adapter ignores send values; tracing must not forward them.
        assert iterator.send("unused") is segments[1]
        with pytest.raises(StopIteration):
            next(iterator)
        assert legacy[0]["completed"] and len(calls) == 1
        observations.append((events, calls[0][1:]))
        if trace:
            assert trace.snapshot()["complete"]
            assert trace.calls[0]["configured_temperature_schedule"] == [0.4]
    assert observations[0] == observations[1]


@pytest.mark.parametrize("operation", ["close", "throw", "source_error"])
def test_trace_preserves_existing_close_and_exception_contract(operation):
    observations = []
    error = RuntimeError("private-error-message")
    for enabled in (False, True):
        trace = metadata.DecoderTrace() if enabled else None
        iterator, segments, events, calls, originals, legacy, _ = fake_decoder(
            trace, error=error if operation == "source_error" else None)
        assert next(iterator) is segments[0]
        if operation == "close":
            iterator.close()
        else:
            with pytest.raises(RuntimeError) as captured:
                iterator.throw(error) if operation == "throw" else next(iterator)
            assert captured.value is error
        # The old tracked loop does not explicitly close/throw into held sources.
        observations.append(list(events))
        assert not legacy[0].get("completed") and len(calls) == 1
        if trace:
            assert not trace.snapshot()["complete"]
            assert "private-error-message" not in json.dumps(trace.snapshot())
        originals[0].close()
    assert observations[0] == observations[1]


def test_trace_hashes_actual_inputs_and_whitelists_private_info():
    trace = metadata.DecoderTrace()
    iterator, _, _, _, _, legacy, audio = fake_decoder(trace)
    list(iterator)
    call = trace.calls[0]
    assert call["pre_vad_audio"]["sha256"] == hashlib.sha256(audio.tobytes()).hexdigest()
    assert call["pre_vad_audio"]["frames"] == 2 and call["pre_vad_audio"]["dtype"] == audio.dtype.str
    assert call["initial_prompt"]["sha256"] == hashlib.sha256(b"private-actual-prompt").hexdigest()
    assert call["initial_prompt"]["char_count"] == len("private-actual-prompt")
    assert call["passed_max_new_tokens"] == 24
    assert call["info_numeric_boolean"] == {"duration": 2.0, "duration_after_vad": 1.25}
    assert call["segments"][0]["token_count"] == 2
    assert call["segments"][0]["token_sha256"] == hashlib.sha256(b"[101,202]").hexdigest()
    assert all(segment["finish_reason"] is None for segment in call["segments"])
    serialized = json.dumps(dict(trace=trace.snapshot(), legacy=legacy))
    assert "private-" not in serialized and "[101, 202]" not in serialized and "[707, 808]" not in serialized
    assert trace.snapshot()["reported_temperature_is_selected_attempt_identity"] is False


def test_metadata_failure_does_not_change_recognition_or_legacy_completion(monkeypatch):
    trace = metadata.DecoderTrace()
    monkeypatch.setattr(trace, "begin", lambda *args: (_ for _ in ()).throw(OSError("private-sink-error")))
    iterator, segments, _, calls, _, legacy, _ = fake_decoder(trace)
    assert list(iterator) == segments and len(calls) == 1 and legacy[0]["completed"]
    snapshot = trace.snapshot()
    assert not snapshot["complete"] and snapshot["failures"] == [{"stage": "call_sink", "exception_class": "OSError"}]
    assert "private-sink-error" not in json.dumps(snapshot)


def test_trace_limit_does_not_truncate_yielded_segments(monkeypatch):
    monkeypatch.setattr(metadata, "MAX_SEGMENTS", 1)
    monkeypatch.setattr(trial, "MAX_SEGMENTS", 1)
    trace = metadata.DecoderTrace()
    iterator, segments, _, _, _, legacy, _ = fake_decoder(trace)
    assert list(iterator) == segments and legacy[0]["completed"]
    assert len(trace.calls[0]["segments"]) == len(legacy[0]["segments"]) == 1
    assert not trace.snapshot()["complete"]


def test_prompt_text_requires_explicit_flag_and_stays_in_metadata(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit):
        trial.main(["--model", str(tmp_path), "--out", str(tmp_path / "unused.json"), "--trace-prompt-text"])
    trace = metadata.DecoderTrace(prompt_text=True)
    iterator, segments, _, _, _, _, _ = fake_decoder(trace)
    assert list(iterator) == segments
    assert trace.calls[0]["initial_prompt"]["text"] == "private-actual-prompt"
    captured = capsys.readouterr()
    assert "private-actual-prompt" not in captured.out + captured.err


def test_opt_in_trace_checkpoint_keeps_default_result_shape_and_restores_patches(monkeypatch, tmp_path):
    monkeypatch.setattr(trial, "local_result_path", lambda path: path)
    monkeypatch.setattr(trial, "model_integrity", lambda path: {"path": str(path), "sha256": {}})
    original_engine = trial.fw_engine.FasterWhisperEngine
    records = []
    writer_shim = lambda path, record: records.append(record)
    monkeypatch.setattr(trial.trial_chunk_window.trial_asr, "write_json", writer_shim)
    def replay(argv):
        trial.trial_chunk_window.trial_asr.write_json(tmp_path / "record.json", {"completed": False, "config": {}})
    monkeypatch.setattr(trial.trial_chunk_window, "main", replay)
    for extra in ([], ["--trace-decoder"]):
        trial.main(["--model", str(tmp_path), "--out", str(tmp_path / "record.json"), *extra])
    assert "decoder_trace" not in records[0]
    assert records[1]["decoder_trace"]["schema"] == "whisper-public-decoder-trace-v1"
    assert not records[1]["decoder_trace"]["complete"]
    assert trial.fw_engine.FasterWhisperEngine is original_engine
    assert trial.trial_chunk_window.trial_asr.write_json is writer_shim

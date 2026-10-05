"""CPU fakes assert native telemetry is transparent at the trial boundary."""
from pathlib import Path
from dataclasses import dataclass
import sys
from types import SimpleNamespace
import hashlib
import json

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import whisper_native_trace as native
import whisper_runtime_trial as trial
from whisper_decoder_trace import DecoderTrace


class NativeModel:
    device = "cuda"
    compute_type = "int8_float32"

    def __init__(self, error=None):
        self.calls, self.outputs = [], []
        self.error = error

    def encode(self, value):
        return value

    def generate(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        result = [SimpleNamespace(sequences_ids=[[901, 902]], scores=[-0.1], no_speech_prob=0.01)]
        self.outputs.append(result)
        return result


class PythonModel:
    def __init__(self, error=None, source_error=None):
        self.model = NativeModel(error)
        self.events, self.prompt_results, self.fallback_results, self.sources = [], [], [], []
        self.encoder = object()
        self.source_error = source_error

    def get_prompt(self, tokenizer, previous_tokens, without_timestamps=False, prefix=None, hotwords=None):
        self.events.append("get_prompt")
        result = previous_tokens + [801, 802]
        self.prompt_results.append(result)
        return result

    def generate_with_fallback(self, encoder_output, prompt, tokenizer, options):
        self.events.append("fallback")
        early = self.model.generate(encoder_output, [prompt], beam_size=5, patience=2.0,
            max_length=24, return_scores=True, suppress_tokens=[777])[0]
        self.model.generate(encoder_output, [prompt], beam_size=1, num_hypotheses=5,
            sampling_temperature=0.4, sampling_topk=0, max_length=24,
            private_unknown="private-value")
        # Installed all-failed selection can return the earlier best result but
        # retain the final attempted temperature. The facade must not repair it.
        result = (early, -0.1, 0.4, 1.0)
        self.fallback_results.append(result)
        return result

    def transcribe(self, audio, temperature=(0.0, 0.4), **kwargs):
        self.events.append("transcribe")
        def segments():
            try:
                prompt = self.get_prompt(object(), [701], prefix="private-prefix", hotwords="private-hotwords")
                result = self.generate_with_fallback(self.encoder, prompt, object(), SimpleNamespace(max_new_tokens=24))
                segment = SimpleNamespace(text="same recognition", tokens=[901, 902], temperature=result[2])
                self.events.append("yield")
                yield segment
                if self.source_error:
                    raise self.source_error
                self.events.append("exhausted")
            finally:
                self.events.append("raw_closed")
        source = segments()
        self.sources.append(source)
        return source, "same-info"


def prepared(enabled, **kwargs):
    model = PythonModel(**kwargs)
    recorder = native.NativeTraceRecorder()
    owner = native.NativeAttemptTrace(model, recorder)
    if enabled:
        owner.__enter__()
    engine = SimpleNamespace(model=model, beam_size=5)
    public = DecoderTrace()
    legacy, _ = trial.configure_decoder(engine, 2.0, "default", trace=public,
        native_trace=owner if enabled else None)
    stream, info = model.transcribe(np.zeros(16, dtype=np.float32), initial_prompt="private-prompt")
    assert info == "same-info" and model.events == ["transcribe"] and not model.model.calls
    return model, recorder, owner, stream, legacy


def test_best_earlier_result_is_distinct_from_final_temperature_and_private(capsys):
    model, recorder, owner, stream, legacy = prepared(True)
    target = model.model._target
    segment = next(stream)
    assert segment.temperature == 0.4 and len(target.calls) == 2
    assert target.calls[0][0][0] is model.encoder
    assert target.calls[0][0][1][0] is model.prompt_results[0]
    assert model.fallback_results[0][0] is target.outputs[0][0]
    with pytest.raises(StopIteration):
        next(stream)
    assert legacy[0]["completed"]
    snapshot = recorder.snapshot()
    assert snapshot["complete"]
    window = snapshot["windows"][0]
    assert window["selected_attempt_index"] == 0 and window["selected_result_index"] == 0
    assert window["selected_attempt_temperature"] == 0.0
    assert window["reported_final_temperature"] == 0.4
    assert window["prompt_index"] == 0 and window["public_call_index"] == 0
    assert snapshot["attempts"][1]["numeric_boolean_kwargs"]["sampling_temperature"] == 0.4
    assert snapshot["attempts"][0]["results"][0]["generated_sequences"][0]["sha256"] == hashlib.sha256(b"[901,902]").hexdigest()
    assert snapshot["attempts"][0]["results"][0]["scores"] == [-0.1]
    assert snapshot["attempts"][0]["results"][0]["no_speech_prob"] == 0.01
    assert all(w["finish_reason"] is None and w["rejection_cause"] is None for w in snapshot["windows"])
    serialized = json.dumps(snapshot)
    assert "private-" not in serialized and "[901, 902]" not in serialized and "777" not in serialized
    assert capsys.readouterr().out == ""
    owner.__exit__(None, None, None)
    assert model.model is target and not ({"get_prompt", "generate_with_fallback", "transcribe"} & vars(model).keys())


@pytest.mark.parametrize("operation", ["exhaust", "close", "throw", "source_error", "native_error"])
def test_off_on_lazy_calls_errors_send_and_close_match(operation):
    observations = []
    error = RuntimeError("private-recognition-error")
    for enabled in (False, True):
        model, recorder, owner, stream, legacy = prepared(enabled,
            error=error if operation == "native_error" else None,
            source_error=error if operation == "source_error" else None)
        target = model.model._target if enabled else model.model
        try:
            if operation == "native_error":
                with pytest.raises(RuntimeError) as caught:
                    next(stream)
                assert caught.value is error
            else:
                segment = next(stream)
                assert segment.text == "same recognition"
                if operation == "close":
                    stream.close()
                elif operation == "throw":
                    with pytest.raises(RuntimeError) as caught:
                        stream.throw(error)
                    assert caught.value is error
                elif operation == "source_error":
                    with pytest.raises(RuntimeError) as caught:
                        next(stream)
                    assert caught.value is error
                else:
                    with pytest.raises(StopIteration):
                        stream.send("ignored by existing tracked loop")
            observations.append((list(model.events), len(target.calls), legacy[0].get("completed")))
            if enabled:
                assert "private-recognition-error" not in json.dumps(recorder.snapshot())
        finally:
            # Keep a reference to original iterator: wrapper must not close it.
            model.sources[0].close()
            if enabled:
                owner.__exit__(None, None, None)
                assert model.model is target
    assert observations[0] == observations[1]


def test_facade_forwards_attributes_calls_and_exact_result_identity():
    model = PythonModel()
    original = model.model
    recorder = native.NativeTraceRecorder()
    with native.NativeAttemptTrace(model, recorder):
        assert model.model.device == original.device and model.model.compute_type == original.compute_type
        marker = object()
        assert model.model.encode(marker) is marker
        model.model.new_attribute = marker
        assert original.new_attribute is marker
        result = model.model.generate(marker, [[1, 2]], beam_size=5)
        assert result is original.outputs[0] and original.calls[0][0][0] is marker
    assert model.model is original


def test_lazy_native_result_is_not_consumed_or_replaced():
    model = PythonModel()
    events = []
    def iterator():
        events.append("consumed")
        yield object()
    source = iterator()
    model.model.generate = lambda *a, **k: source
    recorder = native.NativeTraceRecorder()
    with native.NativeAttemptTrace(model, recorder):
        result = model.model.generate(object(), [[1]])
        assert result is source and not events
    assert not recorder.snapshot()["complete"] and recorder.failures[0]["stage"] == "generate_result"


@pytest.mark.parametrize("failure", ["sink", "attempt_limit", "token_limit"])
def test_metadata_failure_and_limits_leave_recognition_unchanged(monkeypatch, failure):
    if failure == "sink":
        monkeypatch.setattr(native, "token_metadata", lambda _: (_ for _ in ()).throw(OSError("private-sink")))
    elif failure == "attempt_limit":
        monkeypatch.setattr(native, "MAX_ATTEMPTS", 1)
    else:
        monkeypatch.setattr(native, "MAX_TOKENS", 1)
    model, recorder, owner, stream, legacy = prepared(True)
    try:
        assert [s.text for s in stream] == ["same recognition"]
        assert legacy[0]["completed"] and len(model.model.calls) == 2
        assert not recorder.snapshot()["complete"] and recorder.failures
        assert "private-sink" not in json.dumps(recorder.snapshot())
    finally:
        owner.__exit__(None, None, None)


@pytest.mark.parametrize("error", [RuntimeError("failure"), KeyboardInterrupt(), GeneratorExit()])
def test_context_restores_existing_instance_bindings_even_on_cancel(error):
    model = PythonModel()
    model.get_prompt = model.get_prompt
    model.generate_with_fallback = model.generate_with_fallback
    model.transcribe = model.transcribe
    before = dict(vars(model))
    with pytest.raises(type(error)) as caught:
        with native.NativeAttemptTrace(model, native.NativeTraceRecorder()):
            model.transcribe = lambda: None
            raise error
    assert caught.value is error
    assert all(vars(model)[key] is value for key, value in before.items())
    assert vars(model).keys() == before.keys()


def test_native_flag_requires_public_trace_before_loading_model(tmp_path):
    with pytest.raises(SystemExit):
        trial.main(["--model", str(tmp_path), "--out", str(tmp_path / "unused.json"), "--trace-native-attempts"])


def test_reused_native_result_identity_is_ambiguous_not_first_attempt():
    model = PythonModel()
    shared = [SimpleNamespace(sequences_ids=[[901]], scores=[-0.1], no_speech_prob=0.01)]
    model.model.generate = lambda *a, **k: shared
    recorder = native.NativeTraceRecorder()
    with native.NativeAttemptTrace(model, recorder):
        result = model.generate_with_fallback(object(), [801], object(), SimpleNamespace())
        assert result[0] is shared[0] and result[2] == 0.4
    window = recorder.windows[0]
    assert window["selected_attempt_index"] is None and window["selected_attempt_temperature"] is None
    assert window["reported_final_temperature"] == 0.4 and not recorder.snapshot()["complete"]


def test_partial_install_failure_rolls_back_and_keeps_recognition():
    class RefusesPatch(PythonModel):
        def __setattr__(self, name, value):
            if name == "generate_with_fallback":
                raise OSError("private-install-failure")
            super().__setattr__(name, value)
    model = RefusesPatch()
    original = model.model
    recorder = native.NativeTraceRecorder()
    with native.NativeAttemptTrace(model, recorder):
        assert model.model is original
        assert not ({"get_prompt", "generate_with_fallback", "transcribe"} & vars(model).keys())
        assert model.generate_with_fallback(object(), [801], object(), SimpleNamespace())[2] == 0.4
    assert not recorder.snapshot()["complete"]
    assert recorder.failures[0]["stage"] == "native_install"
    assert "private-install-failure" not in json.dumps(recorder.snapshot())


def test_restore_failure_attempts_remaining_bindings_and_preserves_error():
    class RefusesCleanup(PythonModel):
        def __delattr__(self, name):
            if name == "generate_with_fallback":
                raise OSError("private-restore-failure")
            super().__delattr__(name)
    model = RefusesCleanup()
    original = model.model
    recorder = native.NativeTraceRecorder()
    error = RuntimeError("original recognition error")
    with pytest.raises(RuntimeError) as caught:
        with native.NativeAttemptTrace(model, recorder):
            raise error
    assert caught.value is error and model.model is original and "get_prompt" not in vars(model)
    assert recorder.failures[-1]["stage"] == "restore_generate_with_fallback"
    assert not recorder.snapshot()["complete"]


def test_iter_call_scope_restored_after_sink_and_source_failure(monkeypatch):
    model, recorder, owner, stream, _ = prepared(True, source_error=RuntimeError("source error"))
    try:
        monkeypatch.setattr(recorder, "snapshot", lambda: (_ for _ in ()).throw(OSError("sink")))
        assert next(stream).text == "same recognition"
        assert getattr(owner.local, "call", None) is None and getattr(owner.local, "window", None) is None
        with pytest.raises(RuntimeError, match="source error"):
            next(stream)
        assert getattr(owner.local, "call", None) is None and getattr(owner.local, "window", None) is None
        assert recorder.safe("snapshot_sink", recorder.snapshot) is None
    finally:
        owner.__exit__(None, None, None)


def test_simultaneous_owner_rejected_without_affecting_first_owner():
    model = PythonModel()
    target = model.model
    first = native.NativeTraceRecorder()
    second = native.NativeTraceRecorder()
    with native.NativeAttemptTrace(model, first) as owner:
        facade = model.model
        with pytest.raises(ValueError, match="Simultaneous"):
            with native.NativeAttemptTrace(model, second):
                pass
        assert model.model is facade and model._trial_native_trace_owner is owner
        result = model.generate_with_fallback(object(), [801], object(), SimpleNamespace())
        assert result[2] == 0.4
    assert model.model is target and "_trial_native_trace_owner" not in vars(model)
    assert second.failures[0]["stage"] == "native_owner_conflict"


def test_completeness_does_not_hide_missing_bindings_or_public_failure():
    model, recorder, owner, stream, _ = prepared(True)
    try:
        list(stream)
        assert recorder.snapshot(public_complete=True)["complete"]
        assert not recorder.snapshot(public_complete=False)["complete"]
        recorder.windows[0]["prompt_index"] = None
        assert not recorder.snapshot()["complete"]
        recorder.windows[0]["prompt_index"] = 0
        recorder.attempts[0]["window_index"] = None
        assert not recorder.snapshot()["complete"]
    finally:
        owner.__exit__(None, None, None)


def test_final_checkpoint_observes_cleanup_failure_before_publication(monkeypatch, tmp_path):
    class RefusesCleanup(PythonModel):
        def __delattr__(self, name):
            if name == "generate_with_fallback":
                raise OSError("private cleanup error")
            super().__delattr__(name)
    @dataclass
    class Config:
        model: str = "local"
        compute_type: str = "int8_float32"
        cpu_threads: int = 2
        reason: str = "test"
        device: str = "cuda"
    model = RefusesCleanup()
    target = model.model
    monkeypatch.setattr(trial, "local_result_path", lambda path: path)
    monkeypatch.setattr(trial, "model_integrity", lambda path: {"path": str(path), "sha256": {}})
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=object))
    factory = lambda config, **kwargs: SimpleNamespace(config=config, beam_size=5, model=model)
    monkeypatch.setattr(trial.fw_engine, "FasterWhisperEngine", factory)
    records = []
    writer = lambda path, record: records.append(record)
    monkeypatch.setattr(trial.trial_chunk_window.trial_asr, "write_json", writer)
    def replay(argv):
        engine = trial.fw_engine.FasterWhisperEngine(Config())
        segments, _ = engine.model.transcribe(np.zeros(16, dtype=np.float32))
        assert [s.text for s in segments] == ["same recognition"]
        trial.trial_chunk_window.trial_asr.write_json("unused", {"completed": True, "config": {}})
        assert model.model is target
    monkeypatch.setattr(trial.trial_chunk_window, "main", replay)
    trial.main(["--model", str(tmp_path), "--out", str(tmp_path / "unused.json"),
                "--trace-decoder", "--trace-native-attempts"])
    assert len(records) == 1 and records[0]["completed"]
    assert records[0]["decoder_trace"]["complete"]
    native_trace = records[0]["native_decoder_trace"]
    assert not native_trace["complete"]
    assert native_trace["failures"][-1]["stage"] == "restore_generate_with_fallback"
    assert "private cleanup error" not in json.dumps(records)
    assert trial.fw_engine.FasterWhisperEngine is factory
    assert trial.trial_chunk_window.trial_asr.write_json is writer

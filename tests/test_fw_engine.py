"""fw_engine: faster-whisper call parameters, CPU fallback, Windows DLL dirs."""

from types import SimpleNamespace

import numpy as np
import pytest

import fw_engine
from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs
from hw_profile import EngineConfig

CUDA_CFG = EngineConfig("large-v3-turbo", "cuda", "int8_float32", 2, "test")


class FakeWhisperModel:
    instances = []

    def __init__(self, name, device, compute_type, cpu_threads, fail_cuda=False):
        if fail_cuda and device == "cuda":
            raise RuntimeError("Library cublas64_12.dll is not found")
        self.args = (name, device, compute_type, cpu_threads)
        self.calls = []
        FakeWhisperModel.instances.append(self)

    def transcribe(self, audio, **kw):
        self.calls.append((audio, kw))
        segs = [SimpleNamespace(text=" Dear Dr. Patel, "), SimpleNamespace(text="  "),
                SimpleNamespace(text=" thank you for seeing her.")]
        return iter(segs), SimpleNamespace(language="en")


def test_transcribe_parameters_and_join():
    eng = FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel, beam_size=5)
    out = eng.transcribe(np.zeros(16000, dtype=np.float64), prompt="Vocab.")
    assert out == "Dear Dr. Patel, thank you for seeing her."
    audio, kw = eng.model.calls[0]
    assert audio.dtype == np.float32
    assert kw["language"] == "en" and kw["beam_size"] == 5
    assert kw["initial_prompt"] == "Vocab."
    assert kw["vad_filter"] is True and kw["condition_on_previous_text"] is False
    assert kw["without_timestamps"] is True


def test_empty_prompt_passed_as_none():
    eng = FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel)
    eng.transcribe(np.zeros(10, dtype=np.float32), prompt="")
    assert eng.model.calls[0][1]["initial_prompt"] is None


def test_cuda_failure_falls_back_to_cpu_int8():
    factory = lambda *a, **k: FakeWhisperModel(*a, fail_cuda=True, **k)
    eng = FasterWhisperEngine(CUDA_CFG, model_factory=factory)
    assert eng.config.device == "cpu" and eng.config.compute_type == "int8"
    assert eng.model.args[1:3] == ("cpu", "int8")
    assert "cublas" in eng.config.reason


def test_cpu_failure_is_raised():
    def factory(*a, **k):
        raise RuntimeError("model not found")
    with pytest.raises(RuntimeError):
        FasterWhisperEngine(EngineConfig("x", "cpu", "int8", 1, ""), model_factory=factory)


def test_output_capped_by_audio_length_and_window():
    eng = FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel)
    eng.transcribe(np.zeros(16000 * 2, dtype=np.float32), prompt="")
    assert eng.model.calls[-1][1]["max_new_tokens"] == 2 * 10 + 24            # short chunk: small cap
    assert eng.max_new_tokens(30.0, None) == 30 * 10 + 24
    long_prompt = "word " * 600                                             # ~215-token prompt or more
    cap = eng.max_new_tokens(30.0, long_prompt)
    retained = min(eng.count_tokens(long_prompt), fw_engine.WHISPER_PROMPT_TOKEN_LIMIT)
    assert cap + retained + 5 <= fw_engine.WHISPER_MAX_LENGTH
    assert cap > fw_engine.MIN_NEW_TOKENS  # discarded prompt must not starve letter output
    assert eng.max_new_tokens(0.2, None) == fw_engine.MIN_NEW_TOKENS + 2


def test_long_prompt_cap_counts_only_the_tokens_whisper_retains():
    eng = FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel)
    eng.count_tokens = lambda text: 490
    eng.transcribe(np.zeros(30 * 16000, dtype=np.float32), prompt="Dense clinical style.")
    kwargs = eng.model.calls[-1][1]
    assert kwargs["max_new_tokens"] == 220
    assert kwargs["max_new_tokens"] + 223 + 5 == fw_engine.WHISPER_MAX_LENGTH
    assert kwargs["language"] == "en" and kwargs["initial_prompt"] == "Dense clinical style."


def test_default_beam_search_with_patience():
    """Real recordings: beam 5 halves medical errors vs greedy; patience 2 keeps spoken commands."""
    assert fw_engine.DEFAULT_BEAM_SIZE == 5
    eng = FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel)
    eng.transcribe(np.zeros(16000, dtype=np.float32), prompt="")
    kw = eng.model.calls[-1][1]
    assert kw["beam_size"] == 5 and kw["patience"] == 2.0
    greedy = FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel, beam_size=1)
    greedy.transcribe(np.zeros(16000, dtype=np.float32), prompt="")
    assert greedy.model.calls[-1][1]["patience"] == 1.0


def test_beam_size_env(monkeypatch):
    monkeypatch.setenv("MYTRANSCRIBE_BEAM_SIZE", "1")
    assert FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel).beam_size == 1
    monkeypatch.setenv("MYTRANSCRIBE_BEAM_SIZE", "junk")
    assert FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel).beam_size == fw_engine.DEFAULT_BEAM_SIZE


def test_warmup_bypasses_vad_and_survives_errors():
    eng = FasterWhisperEngine(CUDA_CFG, model_factory=FakeWhisperModel)
    eng.warmup()
    assert eng.model.calls[-1][1]["vad_filter"] is False
    eng.model.transcribe = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    eng.warmup()   # logged, not raised


def test_register_cuda_dll_dirs_windows(tmp_path, monkeypatch):
    for lib in ("cublas", "cudnn"):
        (tmp_path / "nvidia" / lib / "bin").mkdir(parents=True)
    (tmp_path / "nvidia" / "cuda_nvrtc").mkdir()          # no bin dir: ignored
    added_calls = []
    monkeypatch.setenv("PATH", "orig")
    added = register_cuda_dll_dirs([str(tmp_path), str(tmp_path / "missing")],
                                   add_dll_directory=added_calls.append, platform="win32")
    assert [p.split("nvidia")[1][1:].split("bin")[0].rstrip("/\\") for p in added] == ["cublas", "cudnn"]
    assert added_calls == added
    import os
    assert os.environ["PATH"].endswith("orig") and "cudnn" in os.environ["PATH"]


def test_register_cuda_dll_dirs_noop_off_windows(tmp_path):
    (tmp_path / "nvidia" / "cublas" / "bin").mkdir(parents=True)
    assert register_cuda_dll_dirs([str(tmp_path)], add_dll_directory=print, platform="linux") == []

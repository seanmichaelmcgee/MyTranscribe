"""hw_profile: model / compute-type selection, especially for the GTX 1060."""

import subprocess

import pytest

from hw_profile import (
    CPU_DEFAULT_MODEL, GPU_DEFAULT_MODEL, GPU_SMALL_VRAM_MODEL,
    HardwareInfo, _query_nvidia_smi, find_nvidia_smi, choose_config, detect_hardware,
    has_slow_fp16, pick_cuda_compute_type,
)

# What CTranslate2 reports on a CC 6.1 card: it advertises float16 (CC >= 5.3)
# even though Pascal fp16 is ~64x slower than fp32.
PASCAL_TYPES = frozenset({"float32", "int8", "int8_float32", "float16", "int8_float16"})
AMPERE_TYPES = PASCAL_TYPES | {"bfloat16", "int8_bfloat16"}


def gtx1060(**kw):
    base = dict(cuda_device_count=1, cuda_compute_types=PASCAL_TYPES,
                gpu_name="NVIDIA GeForce GTX 1060 6GB", vram_mb=6144,
                compute_capability=6.1, cpu_count=4)
    base.update(kw)
    return HardwareInfo(**base)


def test_gtx1060_gets_turbo_int8_float32():
    cfg = choose_config(gtx1060(), env={})
    assert (cfg.model, cfg.device, cfg.compute_type) == (GPU_DEFAULT_MODEL, "cuda", "int8_float32")


def test_gtx1060_detected_by_name_when_driver_lacks_compute_cap():
    hw = gtx1060(compute_capability=None)
    assert has_slow_fp16(hw)
    assert pick_cuda_compute_type(hw) == "int8_float32"


@pytest.mark.parametrize("name", ["NVIDIA GeForce GTX 1070", "GeForce GTX 980 Ti",
                                  "NVIDIA GeForce GTX 1660 SUPER", "Quadro P2000"])
def test_other_slow_fp16_names(name):
    assert has_slow_fp16(HardwareInfo(gpu_name=name))


def test_modern_gpu_uses_int8_float16():
    hw = gtx1060(gpu_name="NVIDIA GeForce RTX 3060", compute_capability=8.6,
                 cuda_compute_types=AMPERE_TYPES, vram_mb=12288)
    assert choose_config(hw, env={}).compute_type == "int8_float16"


def test_unknown_gpu_without_name_or_cc_assumes_fast_fp16():
    hw = gtx1060(gpu_name=None, compute_capability=None)
    assert not has_slow_fp16(hw)


def test_respects_supported_types():
    hw = gtx1060(gpu_name="RTX", compute_capability=8.0,
                 cuda_compute_types=frozenset({"float32", "float16"}))
    assert pick_cuda_compute_type(hw) == "float16"
    hw.cuda_compute_types = frozenset({"float32"})
    assert pick_cuda_compute_type(hw) == "float32"


def test_small_vram_gets_small_model():
    cfg = choose_config(gtx1060(vram_mb=2048, gpu_name="GTX 1050"), env={})
    assert cfg.model == GPU_SMALL_VRAM_MODEL


def test_unknown_vram_still_gets_turbo():
    assert choose_config(gtx1060(vram_mb=None), env={}).model == GPU_DEFAULT_MODEL


def test_cpu_fallback_and_thread_count():
    cfg = choose_config(HardwareInfo(cuda_device_count=0, cpu_count=8), env={})
    assert (cfg.model, cfg.device, cfg.compute_type, cfg.cpu_threads) == (CPU_DEFAULT_MODEL, "cpu", "int8", 7)
    assert choose_config(HardwareInfo(cpu_count=1), env={}).cpu_threads == 1


def test_env_overrides():
    env = {"MYTRANSCRIBE_MODEL": "large-v3", "MYTRANSCRIBE_COMPUTE_TYPE": "int8",
           "MYTRANSCRIBE_CPU_THREADS": "3"}
    cfg = choose_config(gtx1060(), env=env)
    assert (cfg.model, cfg.compute_type, cfg.cpu_threads) == ("large-v3", "int8", 3)


def test_env_force_cpu_and_bad_threads():
    cfg = choose_config(gtx1060(), env={"MYTRANSCRIBE_DEVICE": "CPU", "MYTRANSCRIBE_CPU_THREADS": "x"})
    assert cfg.device == "cpu" and cfg.cpu_threads == 3


class FakeCT2:
    def __init__(self, count=1, types=PASCAL_TYPES, raise_count=False):
        self.count, self.types, self.raise_count = count, types, raise_count

    def get_cuda_device_count(self):
        if self.raise_count:
            raise RuntimeError("cudart64_12.dll not found")
        return self.count

    def get_supported_compute_types(self, device):
        return self.types


def test_detect_hardware_with_gpu():
    smi = lambda: {"name": "NVIDIA GeForce GTX 1060 6GB", "vram_mb": 6144, "compute_capability": 6.1}
    hw = detect_hardware(ct2=FakeCT2(), smi_query=smi)
    assert hw.cuda_device_count == 1 and hw.vram_mb == 6144 and "int8_float32" in hw.cuda_compute_types


def test_detect_hardware_cuda_probe_failure_means_cpu():
    hw = detect_hardware(ct2=FakeCT2(raise_count=True), smi_query=lambda: {})
    assert hw.cuda_device_count == 0
    assert choose_config(hw, env={}).device == "cpu"


def _run_returning(*outputs):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        rc, out = outputs[min(len(calls) - 1, len(outputs) - 1)]
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="")
    return run, calls


def test_nvidia_smi_parse():
    run, _ = _run_returning((0, "NVIDIA GeForce GTX 1060 6GB, 6144, 6.1\n"))
    assert _query_nvidia_smi(run) == {"name": "NVIDIA GeForce GTX 1060 6GB", "vram_mb": 6144,
                                      "compute_capability": 6.1}


def test_nvidia_smi_old_driver_retries_without_compute_cap():
    run, calls = _run_returning((2, ""), (0, "GeForce GTX 1060 6GB, 6078\n"))
    assert _query_nvidia_smi(run) == {"name": "GeForce GTX 1060 6GB", "vram_mb": 6078}
    assert len(calls) == 2 and "compute_cap" not in calls[1][1]


def test_nvidia_smi_missing():
    def run(cmd, **kw):
        raise FileNotFoundError("nvidia-smi")
    assert _query_nvidia_smi(run) == {}


def test_find_nvidia_smi_windows_fallback_path():
    assert find_nvidia_smi(which=lambda n: "/usr/bin/nvidia-smi", exists=lambda p: False) == "/usr/bin/nvidia-smi"
    path = find_nvidia_smi(which=lambda n: None, exists=lambda p: "NVSMI" in p)
    assert path.endswith("NVSMI\\nvidia-smi.exe")
    assert find_nvidia_smi(which=lambda n: None, exists=lambda p: False) is None

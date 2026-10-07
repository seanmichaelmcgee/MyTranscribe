"""
hw_profile.py — pick a faster-whisper model / device / compute type for the
machine MyTranscribe is running on.

Target hardware for the "1060 edition" is an NVIDIA GTX 1060 6 GB (Pascal,
CUDA compute capability 6.1). Pascal has two quirks that drive this module:

  * float16 arithmetic runs at 1/64 of float32 speed on consumer Pascal cards,
    so anything "float16" (including CTranslate2's int8_float16) is slow there
    even though CTranslate2 reports it as supported (it only checks CC >= 5.3).
  * int8 matrix multiply (dp4a) IS fast on CC 6.1, so int8 weights with
    float32 activations ("int8_float32") is the sweet spot: ~1.6 GB VRAM for
    large-v3-turbo, ~3 GB for large-v3.

Everything here is pure / injectable so it can be unit-tested without a GPU.
"""

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("hw_profile")

# Defaults. Override with $MYTRANSCRIBE_MODEL / $MYTRANSCRIBE_COMPUTE_TYPE /
# $MYTRANSCRIBE_DEVICE. MYTRANSCRIBE_MODEL may also be a path to a local
# CTranslate2 model directory (useful for offline installs).
GPU_DEFAULT_MODEL = "large-v3-turbo"
GPU_ACCURATE_MODEL = "large-v3"       # "Best accuracy" option: ~6 points better term recall
GPU_ACCURATE_MIN_VRAM_MB = 5000       # large-v3 int8_float32 peaked at ~3.9 GB whole-card on 6 GB
GPU_SMALL_VRAM_MODEL = "small.en"
GPU_SMALL_VRAM_THRESHOLD_MB = 3500    # below this, turbo+activations gets tight
CPU_DEFAULT_MODEL = "small.en"

# GPU names that are Pascal or older consumer cards (slow float16), used when
# nvidia-smi cannot report compute capability (older drivers).
_SLOW_FP16_NAME_RE = re.compile(
    r"GTX\s*(9\d\d|10\d\d)|GT\s*10\d\d|Quadro\s*P\d|Tesla\s*P(4|40)\b|TITAN\s*X",
    re.IGNORECASE,
)
# GTX 16xx: Turing with fast fp16 but no tensor cores. Measured on a GTX 1660 Ti
# (2026-10-03, 6 alternating runs each): int8_float32 was 26-29 % faster than
# int8_float16 for large-v3 and large-v3-turbo, with the same accuracy.
_INT8_FP32_NAME_RE = re.compile(r"GTX\s*16\d\d", re.IGNORECASE)


@dataclass
class HardwareInfo:
    """What we could learn about the machine. All GPU fields optional."""
    cuda_device_count: int = 0
    cuda_compute_types: frozenset = field(default_factory=frozenset)
    gpu_name: Optional[str] = None
    vram_mb: Optional[int] = None
    compute_capability: Optional[float] = None
    cpu_count: int = 1


@dataclass
class EngineConfig:
    """Everything needed to construct a faster-whisper WhisperModel."""
    model: str
    device: str            # "cuda" or "cpu"
    compute_type: str      # CTranslate2 compute type
    cpu_threads: int
    reason: str            # human-readable explanation, logged at startup


# Older Windows drivers install nvidia-smi here instead of System32 (not on PATH).
_WINDOWS_SMI_FALLBACK = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"


def find_nvidia_smi(which: Callable = shutil.which, exists: Callable = os.path.isfile) -> Optional[str]:
    """Path to nvidia-smi, or None."""
    found = which("nvidia-smi")
    if found:
        return found
    if exists(_WINDOWS_SMI_FALLBACK):
        return _WINDOWS_SMI_FALLBACK
    return None


def _query_nvidia_smi(run: Callable = subprocess.run) -> dict:
    """
    Ask nvidia-smi for name / total memory / compute capability of GPU 0.

    Returns {} if nvidia-smi is missing or fails. compute_cap is only reported
    by drivers >= 510; older drivers make the whole query fail, so we retry
    without it.
    """
    exe = find_nvidia_smi() if run is subprocess.run else "nvidia-smi"
    if exe is None:
        return {}
    for fields in ("name,memory.total,compute_cap", "name,memory.total"):
        try:
            out = run(
                [exe, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.info("nvidia-smi unavailable: %s", exc)
            return {}
        if out.returncode != 0 or not out.stdout.strip():
            continue
        parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
        info = {"name": parts[0]}
        try:
            info["vram_mb"] = int(float(parts[1]))
        except (IndexError, ValueError):
            pass
        if len(parts) > 2:
            try:
                info["compute_capability"] = float(parts[2])
            except ValueError:
                pass
        return info
    return {}


def detect_hardware(ct2=None, smi_query: Callable = _query_nvidia_smi) -> HardwareInfo:
    """
    Probe CUDA via CTranslate2 (no PyTorch needed) and nvidia-smi.

    ct2 / smi_query are injectable for tests.
    """
    if ct2 is None:
        import ctranslate2 as ct2
    info = HardwareInfo(cpu_count=os.cpu_count() or 1)
    try:
        info.cuda_device_count = ct2.get_cuda_device_count()
    except Exception as exc:   # CUDA runtime/DLL problems surface here
        logger.warning("CUDA probe failed (%s); using CPU", exc)
        info.cuda_device_count = 0
    if info.cuda_device_count > 0:
        try:
            info.cuda_compute_types = frozenset(ct2.get_supported_compute_types("cuda"))
        except Exception as exc:
            logger.warning("Could not list CUDA compute types: %s", exc)
        smi = smi_query()
        info.gpu_name = smi.get("name")
        info.vram_mb = smi.get("vram_mb")
        info.compute_capability = smi.get("compute_capability")
    return info


def has_slow_fp16(hw: HardwareInfo) -> bool:
    """True for Pascal-and-older cards where float16 math is crippled."""
    if hw.compute_capability is not None:
        return hw.compute_capability < 7.0
    if hw.gpu_name:
        return bool(_SLOW_FP16_NAME_RE.search(hw.gpu_name))
    return False


def prefers_int8_float32(hw: HardwareInfo) -> bool:
    """Pascal-and-older (slow fp16) and GTX 16xx (no tensor cores): int8_float32 is fastest."""
    return has_slow_fp16(hw) or bool(hw.gpu_name and _INT8_FP32_NAME_RE.search(hw.gpu_name))


def pick_cuda_compute_type(hw: HardwareInfo) -> str:
    """Choose the fastest compute type that is supported and sensible for this GPU."""
    supported = hw.cuda_compute_types
    if prefers_int8_float32(hw):
        preference = ("int8_float32", "int8", "float32")
    else:
        preference = ("int8_float16", "float16", "int8_float32", "int8", "float32")
    for ct in preference:
        if not supported or ct in supported:
            return ct
    return "float32"


def choose_config(hw: HardwareInfo, env: Optional[dict] = None, accurate: bool = False) -> EngineConfig:
    """
    Turn a HardwareInfo into an EngineConfig.

    accurate=True ("Best accuracy" in Options) picks large-v3 instead of
    large-v3-turbo when the GPU has >= GPU_ACCURATE_MIN_VRAM_MB (or unknown VRAM).

    Env overrides win over everything:
      MYTRANSCRIBE_DEVICE        "cpu" forces CPU even if a GPU exists
      MYTRANSCRIBE_MODEL         model name or local model directory
      MYTRANSCRIBE_COMPUTE_TYPE  any CTranslate2 compute type
      MYTRANSCRIBE_CPU_THREADS   int
    """
    env = os.environ if env is None else env
    forced_device = env.get("MYTRANSCRIBE_DEVICE", "").strip().lower()
    use_cuda = hw.cuda_device_count > 0 and forced_device != "cpu"

    if use_cuda:
        device = "cuda"
        compute_type = pick_cuda_compute_type(hw)
        if hw.vram_mb is not None and hw.vram_mb < GPU_SMALL_VRAM_THRESHOLD_MB:
            model = GPU_SMALL_VRAM_MODEL
        elif accurate and (hw.vram_mb is None or hw.vram_mb >= GPU_ACCURATE_MIN_VRAM_MB):
            model = GPU_ACCURATE_MODEL
        else:
            model = GPU_DEFAULT_MODEL
        reason = (
            f"GPU {hw.gpu_name or '?'} (CC {hw.compute_capability or '?'}, "
            f"{hw.vram_mb or '?'} MB): {'slow' if has_slow_fp16(hw) else 'fast'} fp16"
            f"{', best-accuracy model' if model == GPU_ACCURATE_MODEL else ''}"
        )
    else:
        device = "cpu"
        compute_type = "int8"
        model = CPU_DEFAULT_MODEL
        reason = "no usable CUDA device" if forced_device != "cpu" else "CPU forced by env"

    model = env.get("MYTRANSCRIBE_MODEL", "").strip() or model
    compute_type = env.get("MYTRANSCRIBE_COMPUTE_TYPE", "").strip() or compute_type

    try:
        cpu_threads = int(env.get("MYTRANSCRIBE_CPU_THREADS", "0"))
    except ValueError:
        cpu_threads = 0
    if cpu_threads <= 0:
        # Leave one core for audio capture + GUI.
        cpu_threads = max(1, hw.cpu_count - 1) if device == "cpu" else 2

    return EngineConfig(model, device, compute_type, cpu_threads, reason)

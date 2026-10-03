"""
preflight_1060.py — go / no-go checks before an overnight run on the GTX 1060 box.

    venv1060\\Scripts\\python.exe scripts\\preflight_1060.py               (checks + model downloads)
    venv1060\\Scripts\\python.exe scripts\\preflight_1060.py --no-download

Prints one line per check (PASS / WARN / FAIL) and exits non-zero on any FAIL.
Downloads the models the overnight run uses (~6 GB total, one time) unless
--no-download: large-v3-turbo (app default), large-v3, distil-large-v3.5.
"""

import argparse
import importlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

RESULTS = []


def report(level, name, detail=""):
    RESULTS.append(level)
    print(f"[{level}] {name}{': ' + str(detail) if detail else ''}", flush=True)


def check_python():
    v = sys.version_info
    ok = (3, 10) <= (v.major, v.minor) <= (3, 12)
    report("PASS" if ok else "WARN", "Python", f"{sys.version.split()[0]} (tested on 3.11)")


def check_imports():
    for mod, need in (("faster_whisper", True), ("ctranslate2", True), ("PyQt6.QtWidgets", True),
                      ("pyaudio", True), ("pynput", True), ("numpy", True), ("psutil", False),
                      ("rapidfuzz", False), ("jellyfish", False), ("wordfreq", False), ("pytest", False)):
        try:
            m = importlib.import_module(mod)
            report("PASS", f"import {mod}", getattr(m, "__version__", ""))
        except Exception as exc:
            report("FAIL" if need else "WARN", f"import {mod}", exc)


def check_cuda():
    import fw_engine
    added = fw_engine.register_cuda_dll_dirs()
    if sys.platform == "win32":
        report("PASS" if added else "WARN", "pip CUDA DLL folders", f"{len(added)} added")
    import ctranslate2
    try:
        n = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        report("FAIL", "CUDA via ctranslate2", exc)
        return False
    if n == 0:
        report("FAIL", "CUDA via ctranslate2", "0 devices (driver / DLL problem; app would run on CPU)")
        return False
    types = sorted(ctranslate2.get_supported_compute_types("cuda"))
    report("PASS" if any(t.startswith("int8") for t in types) else "WARN", "CUDA compute types", ", ".join(types))
    from hw_profile import choose_config, detect_hardware
    hw = detect_hardware()
    cfg = choose_config(hw)
    # Pascal (GTX 10xx, CC < 7) should get int8_float32; Turing+ (GTX 16xx, RTX) int8_float16.
    from hw_profile import has_slow_fp16
    expected = "int8_float32" if has_slow_fp16(hw) else "int8_float16"
    level = "PASS" if (cfg.device, cfg.compute_type) == ("cuda", expected) else "WARN"
    report(level, "Auto config", f"{cfg.model} {cfg.device} {cfg.compute_type} | {cfg.reason}")
    return True


def check_nvidia_smi():
    from hw_profile import find_nvidia_smi
    smi = find_nvidia_smi()
    if not smi:
        report("WARN", "nvidia-smi", "not found (GPU memory won't be logged)")
        return
    out = subprocess.run([smi, "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu",
                          "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
    report("PASS" if out.returncode == 0 else "WARN", "nvidia-smi", out.stdout.strip() or out.stderr.strip())


def check_audio():
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            info = pa.get_default_input_device_info()
            report("PASS", "Default microphone", info.get("name"))
        except (IOError, OSError):
            report("WARN", "Default microphone", "none (fine for the overnight run: it uses synthetic audio)")
        finally:
            pa.terminate()
    except Exception as exc:
        report("WARN", "PyAudio", exc)


def check_tts():
    if sys.platform == "win32":
        sys.path.insert(0, str(ROOT / "scripts"))
        import make_test_dictation as mtd
        try:
            voices = mtd.sapi_voices()
            report("PASS" if voices else "FAIL", "Windows voices (SAPI)", ", ".join(voices) or "none installed")
        except Exception as exc:
            report("FAIL", "Windows voices (SAPI)", exc)
    else:
        report("PASS" if shutil.which("espeak-ng") else "FAIL", "espeak-ng (Linux TTS)")


def download_models(names):
    from faster_whisper import download_model
    for name in names:
        t0 = time.time()
        try:
            path = download_model(name)
            report("PASS", f"model {name}", f"{path} ({time.time() - t0:.0f}s)")
        except Exception as exc:
            report("FAIL", f"model {name}", exc)


def gpu_smoke(cuda_ok):
    """Load the default model on the GPU and transcribe 10 s of synthetic speech."""
    if not cuda_ok:
        report("WARN", "GPU smoke test", "skipped (no CUDA)")
        return
    import numpy as np
    from fw_engine import FasterWhisperEngine
    from hw_profile import choose_config, detect_hardware
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_test_dictation as mtd
    tmp = ROOT / "results_1060"
    tmp.mkdir(exist_ok=True)
    wav = tmp / "preflight.wav"
    text = "Started apixaban five milligrams twice daily and metformin. Follow up in six weeks."
    try:
        mtd.tts(text, wav, "sapi" if sys.platform == "win32" else "espeak")
        audio, _ = mtd.read_wav(wav)
    except Exception as exc:
        report("WARN", "GPU smoke test audio", f"TTS failed ({exc}); using silence")
        audio = np.zeros(16000 * 5, np.float32)
    try:
        eng = FasterWhisperEngine(choose_config(detect_hardware()))
        eng.warmup()
        t0 = time.time()
        out = eng.transcribe(audio, "Vocabulary: apixaban, metformin.")
        dt = time.time() - t0
        level = "PASS" if eng.config.device == "cuda" else "FAIL"
        report(level, "GPU smoke test", f"{eng.config.device}/{eng.config.compute_type}, "
                                         f"{len(audio) / 16000:.1f}s audio in {dt:.2f}s -> {out!r}")
    except Exception as exc:
        report("FAIL", "GPU smoke test", exc)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Go/no-go checks for the 1060 edition.")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--models", default="large-v3-turbo,large-v3,distil-large-v3.5")
    args = ap.parse_args(argv)
    check_python()
    check_imports()
    check_nvidia_smi()
    cuda_ok = check_cuda()
    check_audio()
    check_tts()
    if not args.no_download:
        download_models([m.strip() for m in args.models.split(",") if m.strip()])
    gpu_smoke(cuda_ok)
    fails, warns = RESULTS.count("FAIL"), RESULTS.count("WARN")
    print(f"\n{'GO' if not fails else 'NO-GO'}: {fails} fail, {warns} warn")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

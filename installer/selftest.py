"""
selftest.py — check an installed (or staged) MyTranscribe from its own Python:

    <install>\\python\\python.exe <install>\\src\\..\\installer_selftest.py   (copied by the build)

Imports what the app needs, loads the speech model the app would choose on this PC, and
transcribes a short generated test tone plus silence (it must load and decode without error;
the text itself is not checked). Prints one line per step and exits non-zero on a failure.
"""

import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))


def step(name, fn):
    t = time.perf_counter()
    try:
        out = fn()
        print(f"[PASS] {name} ({time.perf_counter() - t:.1f} s){': ' + str(out) if out else ''}", flush=True)
        return out
    except Exception as exc:
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)


def imports():
    import ctranslate2, faster_whisper, numpy, pyaudio, pynput, psutil, rapidfuzz, jellyfish, wordfreq  # noqa
    from PyQt6 import QtCore, QtGui, QtWidgets  # noqa
    import gui_med, setup_wizard, options_dialog, drug_names, voice_commands  # noqa  (the whole app)
    return f"python {sys.version.split()[0]} at {sys.executable}"


def text_pipeline():
    """The clean-up steps that need data files and libraries: drug names, vocabulary, commands."""
    import text_fixes
    import voice_commands
    out = voice_commands.apply(text_fixes.finish("She takes Jardientz 25 mg daily comma um no fever period"),
                               lenient=True, punctuation=True)
    if "Jardiance 25 mg daily, no fever." not in out:
        raise AssertionError(out)
    return out


def engine():
    import engines
    eng = engines.build("whisper", accurate=True)
    return eng


def nvidia_libraries():
    """Where the NVIDIA libraries in use were loaded from: inside this copy, or (wrongly) elsewhere on the PC."""
    import psutil
    names = {"cublas64_12.dll", "cublaslt64_12.dll", "cudnn64_9.dll"}
    paths = sorted({m.path for m in psutil.Process().memory_maps() if Path(m.path).name.lower() in names})
    here = str(Path(__file__).resolve().parent).lower()
    outside = [p for p in paths if not p.lower().startswith(here)]
    if outside:
        raise AssertionError("loaded from outside this copy: " + "; ".join(outside))
    return "; ".join(paths) or "none"


def decode(eng):
    import numpy as np
    sr = 16000
    t = np.arange(sr * 2) / sr
    audio = np.concatenate([np.zeros(sr), 0.05 * np.sin(2 * np.pi * 220 * t), np.zeros(sr)]).astype(np.float32)
    eng.transcribe_words(audio, "")
    return "decoded"


if __name__ == "__main__":
    step("imports", imports)
    step("text clean-up", text_pipeline)
    import hw_profile
    hw = step("hardware", lambda: hw_profile.detect_hardware())
    cfg = hw_profile.choose_config(hw, accurate=True)
    print(f"       device={cfg.device} model={cfg.model} threads={cfg.cpu_threads} ({cfg.reason})")
    eng = step("load speech model", engine)
    print(f"       loaded {eng.config.model} on {eng.config.device}/{eng.config.compute_type}, beam {eng.beam_size}")
    step("transcribe", lambda: decode(eng))
    if eng.config.device == "cuda":
        step("NVIDIA libraries", nvidia_libraries)
    print("ALL PASS")

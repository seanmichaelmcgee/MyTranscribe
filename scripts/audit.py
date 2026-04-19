"""
scripts/audit.py — Pre-launch environment audit for MyTranscribe Windows port.

Run from the project root inside the activated venv:
    python scripts/audit.py

Prints one line per check:  [ PASS ] <name>  or  [ FAIL ] <name> — <reason>
Exits with code 0 if every check passes, 1 if any fail.

Derived from docs/port-plan/03-risk-verification.md §3.
"""

import os
import sys
import shutil
import tempfile
import importlib.util
from pathlib import Path

# Windows cmd/PowerShell may default to cp1252; reconfigure to UTF-8 so
# any Unicode in device names or paths prints without crashing.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _result(ok: bool, name: str, detail: str = "") -> bool:
    status = " PASS " if ok else " FAIL "
    suffix = f" — {detail}" if detail and not ok else (f"  ({detail})" if detail else "")
    print(f"[{status}] {name}{suffix}")
    return bool(ok)


def run_audit() -> bool:
    passed = True

    # ------------------------------------------------------------------ #
    # 1. Python version is 3.11.x
    # ------------------------------------------------------------------ #
    vi = sys.version_info
    ok = vi[:2] == (3, 11)
    passed &= _result(ok, "Python version is 3.11.x",
                      f"got {vi.major}.{vi.minor}.{vi.micro}" if not ok
                      else f"{vi.major}.{vi.minor}.{vi.micro}")

    # ------------------------------------------------------------------ #
    # 2. Running inside a virtual environment
    # ------------------------------------------------------------------ #
    in_venv = sys.prefix != sys.base_prefix
    passed &= _result(in_venv, "Running inside a venv",
                      f"sys.prefix={sys.prefix}" if not in_venv else sys.prefix)

    # ------------------------------------------------------------------ #
    # 3. ffmpeg on PATH
    # ------------------------------------------------------------------ #
    ffmpeg_path = shutil.which("ffmpeg")
    passed &= _result(ffmpeg_path is not None, "ffmpeg on PATH",
                      ffmpeg_path or "not found — install ffmpeg and ensure it is on PATH")

    # ------------------------------------------------------------------ #
    # 4. torch / CUDA
    # ------------------------------------------------------------------ #
    try:
        import torch  # noqa: PLC0415
        cuda_ok = torch.cuda.is_available()
        passed &= _result(cuda_ok, "torch.cuda.is_available() is True",
                          f"torch {torch.__version__} / cuda {torch.version.cuda}"
                          if cuda_ok
                          else f"torch {torch.__version__} reports no CUDA — check driver ≥ 550.x")

        if cuda_ok:
            dev_name = torch.cuda.get_device_name(0)
            passed &= _result(bool(dev_name), "torch.cuda.get_device_name(0) returns a name",
                              dev_name or "empty string returned")
        else:
            passed &= _result(False, "torch.cuda.get_device_name(0) returns a name",
                              "skipped — CUDA not available")
    except ImportError as exc:
        passed &= _result(False, "torch importable", str(exc))
        passed &= _result(False, "torch.cuda.is_available() is True", "torch not importable")
        passed &= _result(False, "torch.cuda.get_device_name(0) returns a name", "torch not importable")

    # ------------------------------------------------------------------ #
    # 5. whisper importable
    # ------------------------------------------------------------------ #
    whisper_spec = importlib.util.find_spec("whisper")
    passed &= _result(whisper_spec is not None, "whisper importable",
                      "not found — pip install openai-whisper" if whisper_spec is None else "")

    # ------------------------------------------------------------------ #
    # 6. PyQt6.QtWidgets importable
    # ------------------------------------------------------------------ #
    pyqt6_spec = importlib.util.find_spec("PyQt6.QtWidgets")
    passed &= _result(pyqt6_spec is not None, "PyQt6.QtWidgets importable",
                      "not found — pip install PyQt6" if pyqt6_spec is None else "")

    # ------------------------------------------------------------------ #
    # 7. PyAudio importable AND enumerates ≥1 input device
    # ------------------------------------------------------------------ #
    try:
        import pyaudio  # noqa: PLC0415
        pa = pyaudio.PyAudio()
        input_count = sum(
            1 for i in range(pa.get_device_count())
            if pa.get_device_info_by_index(i).get("maxInputChannels", 0) > 0
        )
        pa.terminate()
        passed &= _result(input_count >= 1, "PyAudio importable and >=1 input device found",
                          f"{input_count} input device(s) found" if input_count >= 1
                          else "no input devices — mic not plugged in or driver missing")
    except ImportError as exc:
        passed &= _result(False, "PyAudio importable and >=1 input device found",
                          f"ImportError: {exc}")
    except Exception as exc:
        passed &= _result(False, "PyAudio importable and >=1 input device found",
                          f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ #
    # 8. pynput importable
    # ------------------------------------------------------------------ #
    pynput_spec = importlib.util.find_spec("pynput")
    passed &= _result(pynput_spec is not None, "pynput importable",
                      "not found — pip install pynput" if pynput_spec is None else "")

    # ------------------------------------------------------------------ #
    # 9. Temp dir writable
    # ------------------------------------------------------------------ #
    td = Path(tempfile.gettempdir())
    probe = td / "mytranscribe_audit_probe.tmp"
    try:
        probe.write_text("ok")
        probe.unlink()
        passed &= _result(True, "Temp dir writable", str(td))
    except Exception as exc:
        passed &= _result(False, "Temp dir writable", f"{td} — {exc}")

    # ------------------------------------------------------------------ #
    # 10. Free disk space on temp dir >=500 MB
    # ------------------------------------------------------------------ #
    try:
        usage = shutil.disk_usage(td)
        free_mb = usage.free / (1024 ** 2)
        ok = free_mb >= 500
        passed &= _result(ok, "Free disk space on temp dir >=500 MB",
                          f"{free_mb:.0f} MB free on {td}"
                          if ok else f"only {free_mb:.0f} MB free on {td} -- need >=500 MB")
    except Exception as exc:
        passed &= _result(False, "Free disk space on temp dir >=500 MB", str(exc))

    # ------------------------------------------------------------------ #
    # 11. Whisper cache dir (~/.cache/whisper) exists or is creatable
    # ------------------------------------------------------------------ #
    whisper_cache = Path.home() / ".cache" / "whisper"
    if whisper_cache.exists():
        passed &= _result(True, "Whisper cache dir exists or is creatable", str(whisper_cache))
    else:
        try:
            whisper_cache.mkdir(parents=True, exist_ok=True)
            passed &= _result(True, "Whisper cache dir exists or is creatable",
                              f"created {whisper_cache}")
        except Exception as exc:
            passed &= _result(False, "Whisper cache dir exists or is creatable",
                              f"cannot create {whisper_cache} — {exc}")

    return passed


if __name__ == "__main__":
    all_passed = run_audit()
    sys.exit(0 if all_passed else 1)

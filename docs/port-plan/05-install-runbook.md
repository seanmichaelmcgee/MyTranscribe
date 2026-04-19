# MyTranscribe — Windows Install Runbook

**Branch:** `claude/windows-port-pyqt6`
**Target machine:** Windows 11, RTX 4070 Ti Super, Python 3.11.x, CUDA 12.4

Every command block in this document is copy-paste executable in **Git Bash** (the
bash shell that ships with Git for Windows). PowerShell syntax is noted where it
differs; all paths use forward slashes unless a `.bat` file is shown.

---

## A. Prerequisites — one-time per machine

Run each verification command; if any fails, fix it before proceeding.

| Requirement | Verify | Minimum |
|---|---|---|
| Python 3.11.x | `python --version` | 3.11.0 |
| ffmpeg on PATH | `ffmpeg -version` | any recent build |
| NVIDIA driver | `nvidia-smi` | 528.xx for CUDA 12.4 (591.74 confirmed working) |
| Git for Windows (bash + gh CLI) | `git --version && gh --version` | any |
| Free disk space | ~10 GB for models + venv | — |

**Python note:** `py -3.11` and `python` must both resolve to Python 3.11. Verify:

```bash
python --version        # should print Python 3.11.x
py -3.11 --version      # same
```

**NVIDIA driver note:** Driver 591.74 (installed on this machine) supports CUDA 12.4
and is confirmed working with torch 2.6.0+cu124. Drivers older than 528.xx will
produce a silent CPU fallback or a `no kernel image` error at first inference.

---

## B. One-time setup from a clean clone

Run these commands in order from a Git Bash terminal.

```bash
# 1. Clone the repository
git clone https://github.com/seanmichaelmcgee/MyTranscribe.git
cd MyTranscribe

# 2. Switch to the Windows port branch
git checkout claude/windows-port-pyqt6

# 3. Create the Python 3.11 virtual environment
py -3.11 -m venv venv

# 4. Upgrade pip and pin setuptools below 81
#    (setuptools >= 81 removed pkg_resources which openai-whisper's build backend
#    still imports; --no-build-isolation in step 6 is the companion guard)
./venv/Scripts/python.exe -m pip install --upgrade pip "setuptools<81" wheel

# 5. Install torch WITH CUDA from the pytorch.org wheel index
#    (torch is NOT in requirements-windows.txt because pip ignores --index-url
#    directives inside requirements files; it must be installed as its own step)
./venv/Scripts/python.exe -m pip install torch==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124

# 6. Install everything else from requirements-windows.txt
#    --no-build-isolation keeps the build in the current venv, so the pinned
#    setuptools<81 from step 4 is visible to openai-whisper's legacy build hook
./venv/Scripts/python.exe -m pip install -r requirements-windows.txt \
    --no-build-isolation
```

---

## C. Verify the install

### Quick smoke checks (run from project root, venv NOT pre-activated)

```bash
# C1 — Python version
./venv/Scripts/python.exe --version
# Expected: Python 3.11.x

# C2 — torch CUDA
./venv/Scripts/python.exe -c \
  "import torch; print('cuda:', torch.cuda.is_available(), '/', torch.version.cuda)"
# Expected: cuda: True / 12.4

# C3 — GPU identity and compute capability
./venv/Scripts/python.exe -c \
  "import torch; print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"
# Expected: NVIDIA GeForce RTX 4070 Ti SUPER (8, 9)

# C4 — Core imports (no DLL errors, no ModuleNotFoundError)
./venv/Scripts/python.exe -c \
  "import PyQt6.QtWidgets, whisper, torch, pyaudio, pynput, numpy; print('imports ok')"
# Expected: imports ok

# C5 — PyQt6 version
./venv/Scripts/python.exe -c \
  "from PyQt6.QtCore import PYQT_VERSION_STR; print('PyQt6', PYQT_VERSION_STR)"
# Expected: PyQt6 6.11.0

# C6 — ffmpeg reachable from within the venv's Python
./venv/Scripts/python.exe -c \
  "import shutil; f=shutil.which('ffmpeg'); print('ffmpeg:', f); assert f, 'NOT FOUND'"
# Expected: ffmpeg: <path to ffmpeg.exe>

# C7 — tempdir writable and not on OneDrive
./venv/Scripts/python.exe -c \
  "import tempfile,pathlib; p=pathlib.Path(tempfile.gettempdir()); \
   (p/'_probe.txt').write_text('ok'); (p/'_probe.txt').unlink(); \
   print('tempdir ok:', p); assert 'OneDrive' not in str(p)"
# Expected: tempdir ok: C:\Users\smich\AppData\Local\Temp  (no OneDrive in path)
```

### Full environment audit (recommended before first real use)

The file `scripts/audit.py` runs all 11 checks in one pass. From the project
root with venv activated:

```bash
source venv/Scripts/activate   # Git Bash activate
python scripts/audit.py
```

All 10 lines must print `[PASS]`. Exit code is 0 on full pass, 1 on any failure.

**Verified results on this machine (2026-04-18):**

```
PyQt6 6.11.0 installed successfully on first attempt.
Smoke test (QMainWindow + QTimer.singleShot 500 ms close) exited with code 0.
Window rendered and closed cleanly — no DLL errors, no Qt platform warnings.
```

---

## D. Run the app

```bash
./venv/Scripts/python.exe src/gui_qt.py
```

> **Note:** `src/gui_qt.py` does not exist yet — it will be created in Phase 3 of
> the implementation plan (`docs/port-plan/01-architecture.md`). The original
> Linux entry point `src/gui-v0.8.py` cannot run on Windows because it depends
> on pycairo and PyGObject (GTK3), which are not installed in the Windows venv.
> Once Phase 3 is complete, `src/gui_qt.py` replaces it as the single entry point.

---

## E. Convenience launcher — `run.bat`

A double-clickable launcher is provided at the repo root as `run.bat`. It activates
the venv and launches the app — no terminal interaction needed:

```batch
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python src\gui_qt.py
```

`cd /d "%~dp0"` ensures the working directory is always the project root regardless
of how the file was launched (Start Menu pin, desktop shortcut, Windows Explorer
double-click, or a shortcut whose "Start in" field points elsewhere). This prevents
the `cwd = C:\Windows\System32` bug described in risk R15.

---

## F. Troubleshooting

### `torch.cuda.is_available()` returns `False`

The most common cause is an NVIDIA driver older than 528.xx. Check:

```bash
nvidia-smi   # prints driver version in top-right corner
```

If the driver is below 528, update via GeForce Experience or download from
[nvidia.com/drivers](https://www.nvidia.com/drivers). After updating, re-run C2
above. If the driver version is current but CUDA is still unavailable, verify that
torch was installed from the correct index URL (pytorch.org/whl/cu124, not PyPI):

```bash
./venv/Scripts/python.exe -m pip show torch   # version must end in +cu124
```

If it shows `2.6.0` without `+cu124`, reinstall using the command in step B5.

### PyAudio cannot find an input device / `-9996 Invalid input device`

1. Open **Windows Settings → System → Sound → Input** and confirm the microphone
   is listed and not muted.
2. Open **Settings → Privacy & security → Microphone** and ensure
   "Let apps access your microphone" is On and Python/terminal is not blocked.
3. If using a USB microphone, unplug and replug it, then relaunch — Windows
   PortAudio device indexes shift on hot-plug (risk R03).
4. If another app (Discord, Teams, Zoom) has the mic in exclusive mode, close it
   and retry (risk R35).

Run the device enumeration one-liner from test T04 to see all visible input
devices and their host APIs:

```bash
./venv/Scripts/python.exe -c \
  "import pyaudio; p=pyaudio.PyAudio(); \
   [print(i, p.get_device_info_by_index(i)['name'], \
          p.get_device_info_by_index(i)['maxInputChannels'], \
          p.get_host_api_info_by_index(p.get_device_info_by_index(i)['hostApi'])['name']) \
    for i in range(p.get_device_count()) \
    if p.get_device_info_by_index(i)['maxInputChannels']>0]"
```

### PyQt6 DLL load error (`ImportError: DLL load failed`)

PyQt6's Qt6 DLLs depend on the Microsoft Visual C++ 2015–2022 Redistributable
(x64). Install it with:

```bash
winget install Microsoft.VCRedist.2015+.x64
```

Then relaunch. This redistributable is usually already present on machines with
Visual Studio, modern Office, or recent games installed, but may be missing on
a clean Windows install.

### `pynput` global hotkey (Ctrl+Alt+Q) not firing from other apps

Four known causes in order of likelihood:

1. **Antivirus / EDR blocking the low-level keyboard hook.** Windows Defender and
   Malwarebytes sometimes flag `pynput`'s `keyboard.Listener` as a keylogger.
   Check Windows Security → Protection history for a recent blocked event. If
   flagged, add the project directory to Defender exclusions:
   *Windows Security → Virus & threat protection → Manage settings →
   Exclusions → Add an exclusion → Folder → select `C:\Users\smich\Apps\MyTranscribe`*.

2. **Focus Assist (Do Not Disturb) mode active.** Focus Assist can suppress
   low-level hooks in some configurations. Turn it off temporarily and retry.

3. **Foreground app is running elevated (as Administrator).** Windows prevents
   unelevated low-level hooks from observing input directed at an elevated window
   (UAC security boundary — risk R05). Task Manager, regedit, and any
   "Run as administrator" app will swallow the hotkey. This is a documented
   limitation with no workaround short of running MyTranscribe as admin.

4. **Ctrl+Alt+Q stolen by another app.** Google Meet in Chrome and some IDE
   plugins register this combo. Close the competing app or change the hotkey
   (risk R07).

---

## G. Uninstall / reset

To remove the virtual environment and start fresh:

```bash
rm -rf venv
```

To also remove cached Whisper models (1–10 GB depending on which models were
downloaded):

```bash
rm -rf ~/.cache/whisper
```

(`~/.cache/whisper` maps to `C:\Users\smich\.cache\whisper` on this machine.
The models are re-downloaded automatically on first use after deletion.)

To remove the repository entirely:

```bash
cd ..
rm -rf MyTranscribe
```

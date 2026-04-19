# MyTranscribe

Real-time, GPU-accelerated speech transcription for Linux and Windows.

![Version](https://img.shields.io/badge/version-0.10-blue)
![Python](https://img.shields.io/badge/python-3.11-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## Overview

MyTranscribe is a lightweight desktop application that transcribes spoken audio in
real time using OpenAI's Whisper model. It runs in a small always-on-top window with
0.9 opacity so it stays out of the way while remaining visible. Transcribed text is
copied to the clipboard automatically after each segment.

The app is optimized for English. Other languages work — Whisper is multilingual by
design — but accuracy will vary and has not been systematically tested in this
configuration.

Two recording modes are available: normal mode processes audio in rolling 5-minute
chunks so transcription is continuous and low-latency; long recording mode captures
an extended utterance as one uninterrupted segment before processing it. GPU
acceleration (NVIDIA CUDA) is used when available, reducing per-segment inference
time to under one second on a mid-range card.

Linux (GTK3) and Windows (PyQt6) are both first-class targets. The two entry points
share the same transcription engine (`src/transcriber_v12.py`).

---

## Features

- Real-time transcription powered by OpenAI Whisper, with results copied to the
  clipboard after every segment
- GPU acceleration via NVIDIA CUDA; CPU fallback is automatic when no GPU is present
- Model selection from `tiny` to `large-v3`, plus the `turbo` distilled model
  (~8× faster than `large-v3` at comparable quality) — configurable via the
  `MYTRANSCRIBE_MODEL` environment variable
- Two recording modes: **Normal** (continuous 5-minute auto-chunking) and **Long**
  (single extended capture up to 3 minutes, processed on Stop)
- Global hotkey **Ctrl+Alt+Q** — triggers Start/Stop from any application
- **Spacebar** shortcut when the MyTranscribe window is focused
- Always-on-top window at 0.9 opacity for unobtrusive monitoring
- Audio activity indicator (green status bar) and chime feedback so you can tell
  when transcription starts or stops without watching the window
- Technical-vocabulary prompt primes Whisper with programming and ML terminology to
  improve accuracy on code-heavy speech
- Cross-platform: GTK3 interface on Linux (`src/gui-v0.8.py`), PyQt6 interface on
  Windows (`src/gui_qt.py`)

---

## Hardware expectations

Whisper model weights are loaded entirely onto the GPU. The table below gives
approximate VRAM requirements and a rough quality/speed characterisation. All VRAM
figures are approximate at fp16 precision; actual reservation may be higher due to
PyTorch memory pooling.

| Model | Approx. VRAM | Relative speed | Notes |
|---|---|---|---|
| `tiny` | ~1 GB | Fastest | Acceptable for clear speech, degrades badly on accented or noisy audio |
| `base` | ~1 GB | Very fast | Better than `tiny`; good starting point for weak GPUs |
| `small` | ~2 GB | Fast | Default on Linux; solid accuracy for most technical speech |
| `medium` | ~5 GB | Moderate | Good accuracy step-up over `small` |
| `large-v3` | ~6–9 GB† | Slower | Default on Windows; best accuracy for complex vocabulary |
| `turbo` | ~6 GB | ~8× faster than `large-v3` | Distilled large-v3; near-large accuracy at much lower latency |

† On an RTX 4070 Ti Super (16 GB), `large-v3` measured ~5.88 GB allocated /
9.15 GB reserved at steady state.

**CPU fallback:** CUDA is not available on all machines. When no GPU is detected,
Whisper runs on the CPU. Expect roughly 5–10× real-time (a 30-second recording
may take 3–5 minutes to process on a modern desktop CPU). CPU mode is functional
but not recommended for interactive use; if this is your constraint, choose `tiny`
or `base` to keep turnaround tolerable.

**Tested configurations:**

- Ubuntu 24.04 — NVIDIA GeForce GTX 1660 Ti (6 GB VRAM) + Intel Core i7-9xxx —
  `small` model
- Windows 11 — NVIDIA GeForce RTX 4070 Ti Super (16 GB VRAM) — `large-v3` model

---

## Installation — Linux

### System dependencies

Install GTK3, PortAudio, and Cairo development headers before creating the venv.
On Ubuntu/Debian one command covers all required libraries:

```bash
sudo apt-get update
sudo apt-get install libcairo2-dev pkg-config python3-dev \
    libgirepository1.0-dev portaudio19-dev ffmpeg \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

On macOS, use `brew install pygobject3 gtk+3 portaudio ffmpeg`.

See `System_dependencies.md` for a description of each library's role and for
ALSA/JACK troubleshooting if your microphone is not detected after install.

### Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip "setuptools<81" wheel
pip install -r requirements.txt
```

The `requirements.txt` includes `openai-whisper`, `PyAudio`, `pynput`, `numpy`,
`pycairo`, and `PyGObject`, plus all CUDA-linked `nvidia-*-cu12` packages.
PyTorch (CUDA 12.4 build) is listed directly in `requirements.txt` for Linux.

---

## Installation — Windows

### Prerequisites

Before running the install commands, confirm these are in place:

| Requirement | Check command | Minimum |
|---|---|---|
| Python 3.11.x | `python --version` | 3.11.0 |
| ffmpeg on PATH | `ffmpeg -version` | any recent build |
| NVIDIA driver | `nvidia-smi` | 528.xx (591.74 confirmed with CUDA 12.4) |

Install ffmpeg with winget if needed: `winget install Gyan.FFmpeg`

### Install steps

Run these in Git Bash from the repository root:

```bash
# 1. Create a Python 3.11 virtual environment
py -3.11 -m venv venv

# 2. Upgrade pip and pin setuptools below 81
#    (setuptools >= 81 dropped pkg_resources, which openai-whisper's
#    build backend still requires; --no-build-isolation in step 4 is
#    the companion guard)
./venv/Scripts/python.exe -m pip install --upgrade pip "setuptools<81" wheel

# 3. Install PyTorch with CUDA 12.4 from the pytorch.org wheel index
#    (torch is NOT in requirements-windows.txt — pip ignores --index-url
#    inside requirements files reliably; it must be its own step)
./venv/Scripts/python.exe -m pip install torch==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124

# 4. Install everything else
./venv/Scripts/python.exe -m pip install -r requirements-windows.txt \
    --no-build-isolation
```

For PowerShell, replace `./` with `.\` in the paths above:

```powershell
.\venv\Scripts\python.exe -m pip install --upgrade pip "setuptools<81" wheel
.\venv\Scripts\python.exe -m pip install torch==2.6.0 `
    --index-url https://download.pytorch.org/whl/cu124
.\venv\Scripts\python.exe -m pip install -r requirements-windows.txt `
    --no-build-isolation
```

### Verify the install

Run the environment audit script (11 checks, exits 0 on full pass):

```bash
source venv/Scripts/activate   # Git Bash
python scripts/audit.py
```

Every line should print `[ PASS ]`. See
`docs/port-plan/05-install-runbook.md` for the full runbook including manual
smoke-test commands and a detailed troubleshooting section (§F).

---

## First run and model download

Whisper downloads model weights on first use and caches them locally:

- Linux / macOS: `~/.cache/whisper`
- Windows: `%USERPROFILE%\.cache\whisper`

`large-v3` weights are approximately 2.9 GB; `turbo` is similar. The download
is one-time; subsequent launches load from the cache.

On first start, expect a log sequence similar to:

```
CUDA device: NVIDIA GeForce RTX 4070 Ti SUPER
Loading Whisper model 'large-v3' on cuda:0 …
Model loaded in 8.2 s
CUDA warmup complete — first inference ready
```

After the warmup, the first real inference typically completes in 0.5–1 second
on an RTX 4070 Ti Super. A longer initial pause (up to 10 seconds) on first
`Start` is normal and is not a hang — CUDA JIT-compiles the model kernels on
first use.

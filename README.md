# MyTranscribe

Real-time, GPU-accelerated speech transcription for Linux and Windows.

![Version](https://img.shields.io/badge/version-0.10-blue)
![Python](https://img.shields.io/badge/python-3.11-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## Overview

MyTranscribe is a lightweight desktop application that transcribes spoken audio in
real time using OpenAI's Whisper model. It runs in a small always-on-top window at
0.9 opacity, staying out of the way while remaining visible. Transcribed text is
copied to the clipboard automatically after each segment.

The app is optimized for English — Whisper is multilingual, but accuracy on other
languages has not been systematically tested in this configuration.

Normal mode processes audio in rolling 5-minute chunks for continuous, low-latency
transcription. Long recording mode captures an extended utterance as one segment
before processing. GPU acceleration (NVIDIA CUDA) cuts per-segment inference to
under a second on a mid-range card.

Linux (GTK3) and Windows (PyQt6) are both first-class targets sharing the same
transcription engine (`src/transcriber_v12.py`). Built primarily through iterative
work with consumer-level LLMs: OpenAI o3-mini-high, GPT-4o, and Claude 3.7 Thinking.

---

## Features

- Real-time transcription powered by OpenAI Whisper, with results copied to the
  clipboard after every segment
- GPU acceleration via NVIDIA CUDA; CPU fallback is automatic when no GPU is present
- Model selection from `tiny` to `large-v3`, plus the `turbo` distilled model
  (~8x faster than `large-v3` at comparable quality) — configurable via the
  `MYTRANSCRIBE_MODEL` environment variable on both platforms
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

## Hardware Expectations

Whisper model weights are loaded entirely onto the GPU. The table below gives
approximate VRAM requirements and a rough quality/speed characterisation. All VRAM
figures are approximate at fp16 precision; actual reservation may be higher due to
PyTorch memory pooling.

| Model | Approx. VRAM | Relative speed | Notes |
|---|---|---|---|
| `tiny` | ~1 GB | Fastest | Acceptable for clear speech; degrades on accented or noisy audio |
| `base` | ~1 GB | Very fast | Better than `tiny`; good starting point for weak GPUs |
| `small` | ~2 GB | Fast | Default on Linux; solid accuracy for most technical speech |
| `medium` | ~5 GB | Moderate | Good accuracy step-up over `small` |
| `large-v3` | ~6–9 GB† | Slower | Default on Windows; best accuracy for complex vocabulary |
| `turbo` | ~6 GB | ~8x faster than `large-v3` | Distilled large-v3; near-large accuracy at much lower latency |

† On an RTX 4070 Ti Super (16 GB), `large-v3` measured ~5.88 GB allocated /
9.15 GB reserved at steady state.

**CPU fallback:** When no GPU is detected, Whisper runs on the CPU. Expect roughly
5–10x real-time (a 30-second recording may take 3–5 minutes on a modern desktop
CPU). CPU mode is functional but not recommended for interactive use; if this is
your constraint, choose `tiny` or `base` to keep turnaround tolerable.

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
py -3.11 -m venv venv
./venv/Scripts/python.exe -m pip install --upgrade pip "setuptools<81" wheel

# torch must be installed separately with the pytorch.org index URL
./venv/Scripts/python.exe -m pip install torch==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124

# setuptools<81 note: openai-whisper's build backend requires pkg_resources;
# --no-build-isolation is the companion guard
./venv/Scripts/python.exe -m pip install -r requirements-windows.txt \
    --no-build-isolation
```

For PowerShell, replace `./` with `.\` in all paths above.

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

## First Run and Model Download

Whisper downloads model weights on first use and caches them locally:

- Linux / macOS: `~/.cache/whisper`
- Windows: `%USERPROFILE%\.cache\whisper`

`large-v3` weights are approximately 2.9 GB; `turbo` is similar. The download
is one-time; subsequent launches load from the cache.

On first start, expect a log sequence similar to:

```
CUDA device: NVIDIA GeForce RTX 4070 Ti SUPER
Loading Whisper model 'large-v3' on cuda:0 ...
Model loaded in 8.2 s
CUDA warmup complete — first inference ready
```

After the warmup, the first real inference typically completes in 0.5–1 second
on an RTX 4070 Ti Super. A longer initial pause (up to 10 seconds) on first
`Start` is normal and is not a hang — CUDA JIT-compiles the model kernels on
first use.

---

## Launch Workflows

With install complete, here is the recommended way to launch on each platform.

### Linux

Add a single alias to `~/.bashrc` or `~/.zshrc`:

```bash
alias MyTranscribe='cd /path/to/MyTranscribe && source venv/bin/activate && python src/gui-v0.8.py'
```

Replace `/path/to/MyTranscribe` with the absolute path of your clone. Then reload the file once:

```bash
source ~/.bashrc   # or source ~/.zshrc
```

From that point on, typing `MyTranscribe` in any terminal activates the venv and
launches the app. The alias lives entirely outside the repo, so `git pull` will
never clobber it.

For desktop-menu integration (GNOME Activities, KDE application launcher), create
a `.desktop` file at `~/.local/share/applications/mytranscribe.desktop`:

```ini
[Desktop Entry]
Name=MyTranscribe
Exec=bash -c "cd /path/to/MyTranscribe && source venv/bin/activate && python src/gui-v0.8.py"
Type=Application
Comment=Real-time speech transcription
Terminal=false
Categories=Utility;AudioVideo;
```

### Windows

1. Open File Explorer and navigate to the project root.
2. Right-click `run.bat` and choose **Show more options → Send to → Desktop (create shortcut)**
   (or **Create shortcut** and then drag it to the Desktop).
3. Double-click the shortcut. `run.bat` activates the venv and starts `src\gui_qt.py`;
   the console window is unobtrusive and can be minimized.

`run.bat` content for reference:

```bat
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python src\gui_qt.py
```

The `cd /d "%~dp0"` line means the shortcut's "Start in" field is irrelevant —
`run.bat` always resolves paths relative to its own location.

Optional polish — give the shortcut a recognizable icon:

1. Right-click the new desktop shortcut → **Properties**.
2. Click **Change Icon...**.
3. Browse to `C:\Windows\System32\shell32.dll` and pick an audio- or microphone-looking
   icon (index 168 is a speaker).
4. Click **OK → Apply**.

For a terminal-friendly launch that mirrors the Linux alias, add a function to your
PowerShell `$PROFILE` — see Microsoft's documentation for the `$PROFILE` variable.

---

## Usage — Controls

### Buttons

| Button | State when active | Action |
|---|---|---|
| **Start** (green) | Idle | Begins normal recording. Audio is transcribed in rolling 5-minute chunks. |
| **Long Record** (blue) | Idle | Begins a long-format recording session. Processes up to 3 minutes of audio in a single pass. |
| **Stop** (red) | Normal Recording or Long Recording | Ends the active session, finalises transcription, and copies the result to the clipboard. |

### Keyboard shortcuts

| Input | Condition | Effect |
|---|---|---|
| **Spacebar** | Window focused, Idle | Start normal recording |
| **Spacebar** | Window focused, Normal Recording | Stop normal recording |
| **Spacebar** | Window focused, Long Recording | No-op — see note below |
| **Ctrl+Alt+Q** | Any focused app, Idle | Start normal recording; brings MyTranscribe window forward |
| **Ctrl+Alt+Q** | Any focused app, Normal Recording | Stop normal recording |
| **Ctrl+Alt+Q** | Any focused app, Long Recording | No-op — see note below |

> **Long Recording safety guard**
>
> While Long Recording is active, Spacebar and Ctrl+Alt+Q are deliberately inert.
> Only the **Stop button** can end a long session. This prevents a stray keypress
> (or the hotkey combo appearing in a meeting transcript) from silently discarding
> a long recording. Bring the MyTranscribe window to the foreground and click **Stop**.

### Clipboard and audio feedback

When a recording stops, the full transcription is copied to the clipboard
automatically — paste with **Ctrl+V**. If the recording captures no speech
(silent input or RMS below threshold), the clipboard is not overwritten; the last
successful transcription remains available.

A short chime plays on start and stop so you can work in another app and still
hear state changes. A dark-green activity indicator pulses in the text-area corner
while speech above the RMS threshold is detected.

---

## Model Selection

The Whisper model is controlled by the `MYTRANSCRIBE_MODEL` environment variable.
This works on **both Linux and Windows** as of commit `832a697`.

### Available models

```
tiny   tiny.en   base   base.en   small   small.en
medium   medium.en   large-v1   large-v2   large-v3
large   large-v3-turbo   turbo
```

The `.en` variants are English-only; they are slightly faster and more accurate for
English-only use.

### Defaults

| Platform | Default model | Rationale |
|---|---|---|
| Linux (`gui-v0.8.py`) | `small` | Original hardware sweet spot (NVIDIA 1660 Ti / 6 GB VRAM) |
| Windows (`gui_qt.py`) | `large-v3` | Tuned for the 4070 Ti Super (16 GB VRAM); falls back to CPU if CUDA is unavailable |

### Setting the model

**Linux:**

```bash
MYTRANSCRIBE_MODEL=turbo MyTranscribe
```

**Windows (PowerShell, per-session):**

```powershell
$env:MYTRANSCRIBE_MODEL = 'turbo'; .\run.bat
```

**Windows (persistent, via shortcut Target field):**

Open the shortcut's Properties and change the **Target** field to:

```batch
cmd /c "set MYTRANSCRIBE_MODEL=turbo && C:\path\to\MyTranscribe\run.bat"
```

### Choosing a model

- **tiny / base** — Use on weak GPUs (4 GB VRAM or less) or when CPU fallback is
  your only option. Accuracy is lower; latency is minimal.
- **small / medium** — Balanced trade-off. `small` covers the tested 1660 Ti
  configuration. `medium` gives noticeably better accuracy if you have 5+ GB VRAM free.
- **large-v3** — Highest accuracy. Requires approximately 8–10 GB VRAM (measured
  7–9 GB at fp16 on the 4070 Ti Super). Recommended if you have the hardware.
- **turbo** — A distilled large-v3 that is approximately 8x faster with a minor
  accuracy cost. Good choice when you want large-v3 quality on less VRAM (~6 GB)
  or when transcription latency matters more than marginal accuracy.

---

## Troubleshooting

Full troubleshooting detail is in `docs/port-plan/05-install-runbook.md` §F. The
items below cover the issues most likely to surface in a fresh install.

**`torch.cuda.is_available()` returns `False` (driver mismatch)**

Run `nvidia-smi` and check the driver version. Drivers older than 528.xx produce a
silent CPU fallback or a `no kernel image` error. Update via GeForce Experience or
[nvidia.com/drivers](https://www.nvidia.com/drivers). Also confirm torch was
installed from the pytorch.org wheel index (version string must end in `+cu124`).

**PyAudio cannot find the microphone (`-9996 Invalid input device`)**

On Windows, check **Settings → Privacy & security → Microphone** → "Let apps access
your microphone". Verify the device is not muted in **System → Sound → Input**. If
Discord, Teams, or Zoom holds the mic in exclusive mode, close it and retry. On
Linux, run `arecord -l` to list ALSA devices; see `System_dependencies.md` for
ALSA/JACK guidance.

**`ffmpeg: FileNotFoundError`**

Install ffmpeg (`sudo apt-get install ffmpeg` on Ubuntu; `winget install Gyan.FFmpeg`
on Windows), verify with `ffmpeg -version` in a fresh terminal, then relaunch.

**Ctrl+Alt+Q global hotkey not firing**

On Windows: (1) antivirus/EDR may block `pynput` — add the project folder to
Defender exclusions; (2) if the foreground app is elevated (Task Manager, regedit),
pynput running unelevated cannot intercept it — run MyTranscribe as admin or switch
focus to a non-elevated window; (3) another app has claimed the combo; (4) Focus
Assist is active. On Linux: pynput on Wayland requires XWayland — set
`GDK_BACKEND=x11` or switch to an X11 session.

**Transcription silent despite speech (RMS threshold)**

The startup log shows an RMS value per chunk. If it is consistently below 80, lower
the threshold in `transcriber_v12.py`. Also confirm the correct input device is
selected — the Windows device index can shift when USB devices are plugged in.

**DLL load error on Windows PyQt6 (`ImportError: DLL load failed`)**

Install the Microsoft Visual C++ 2015–2022 Redistributable (x64):

```powershell
winget install Microsoft.VCRedist.2015+.x64
```

**OneDrive tempdir**

If `%TEMP%` resolves to a OneDrive-synced path, Whisper's temporary files may
trigger sync conflicts. Verify with `python scripts/audit.py` (check C7) and
redirect `%TEMP%` to a local path in your shortcut's environment if needed.

---

## Project Structure

```
MyTranscribe/
├── src/
│   ├── gui-v0.8.py              # Linux entry point (GTK3 / PyGObject)
│   ├── gui_qt.py                # Windows entry point (PyQt6)
│   ├── transcriber_v12.py       # Shared audio capture + Whisper backend
│   └── sound_utils.py           # Chime generator and player
├── scripts/
│   └── audit.py                 # Windows environment verification (11 checks)
├── docs/
│   └── port-plan/               # Windows port design, risk register, verification docs
│       ├── 01-architecture.md
│       ├── 02-ux-contract.md
│       ├── 05-install-runbook.md
│       └── 07-human-verification.md
├── requirements.txt             # Linux Python dependencies
├── requirements-windows.txt     # Windows Python dependencies
├── run.bat                      # Windows double-click launcher
├── System_dependencies.md       # Linux system packages + ALSA/JACK guidance
└── WINDOWS_PORT_PLAN_DETAILED.md
```

The two entry points share `transcriber_v12.py` (audio recording, VAD, Whisper
inference) and `sound_utils.py` (chime synthesis). All UI and hotkey code lives
in the platform-specific entry point.

---

## License

This project is licensed under the MIT License — see the LICENSE file for details.

## Acknowledgements

- [OpenAI Whisper](https://github.com/openai/whisper) — speech recognition model
- [PyTorch](https://pytorch.org/) — GPU acceleration and tensor operations
- [GTK](https://www.gtk.org/) — user interface framework (Linux entry point)
- [PyQt6](https://riverbankcomputing.com/software/pyqt/) / [Qt](https://www.qt.io/) — user interface framework (Windows entry point)
- [pynput](https://github.com/moses-palmer/pynput) — global keyboard listener (Ctrl+Alt+Q hotkey)
- [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/) — cross-platform audio I/O

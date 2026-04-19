<!-- Sonnet B — sections 8–13 of the new README.md -->
<!-- Do NOT edit README.md directly; stitch agent combines A + B. -->

## Launch workflows

### Linux

Add a single alias to `~/.bashrc` or `~/.zshrc`:

```bash
alias MyTranscribe='cd /path/to/MyTranscribe && source venv/bin/activate && python src/gui-v0.8.py'
```

Replace `/path/to/MyTranscribe` with the absolute path of your clone. Then reload the file once:

```bash
source ~/.bashrc   # or source ~/.zshrc
```

From that point on, typing `MyTranscribe` in any terminal activates the venv and launches the app. The alias lives entirely outside the repo, so `git pull` will never clobber it.

For desktop-menu integration (GNOME Activities, KDE application launcher), a `.desktop` file is the idiomatic alternative — the template is in the current README under §Creating-a-Desktop-Shortcut.

### Windows

1. Open File Explorer and navigate to the project root (`C:\Users\smich\Apps\MyTranscribe` or wherever you cloned it).
2. Right-click `run.bat` and choose **Show more options → Send to → Desktop (create shortcut)** (or **Create shortcut** and then drag it to the Desktop).
3. Double-click the shortcut. The `run.bat` launcher activates the venv and starts `src\gui_qt.py`; the console window is unobtrusive and can be minimized.

Optional polish — give the shortcut a recognizable icon:

1. Right-click the new desktop shortcut → **Properties**.
2. Click **Change Icon...**.
3. Browse to `C:\Windows\System32\shell32.dll` and pick an audio- or microphone-looking icon (index 168 is a speaker; index 178 is a telephone; pick whichever fits).
4. Click **OK → Apply**.

For a terminal-friendly launch that mirrors the Linux alias pattern, a function in your PowerShell `$PROFILE` is a clean alternative — no template needed here; see the Windows PowerShell `$PROFILE` documentation.

---

## Usage — controls

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
| **Spacebar** | Window focused, **Long Recording** | **No-op — see note below** |
| **Ctrl+Alt+Q** | Any focused app, Idle | Start normal recording; brings MyTranscribe window forward |
| **Ctrl+Alt+Q** | Any focused app, Normal Recording | Stop normal recording |
| **Ctrl+Alt+Q** | Any focused app, **Long Recording** | **No-op — see note below** |

> **Long Recording safety guard**
>
> While Long Recording is active, both the Spacebar and Ctrl+Alt+Q are deliberately inert. Only the **Stop button** can end a long session.
>
> The reasoning: long recording is a ≥3-minute commitment. If Space or the global hotkey could end it, a stray keypress while typing in another app (or the hotkey combo appearing in a meeting transcript) would silently discard your recording. Mouse-only stop is the intentional design. To end a long session, bring the MyTranscribe window to the foreground and click **Stop**.

### Clipboard behaviour

- When a recording stops normally, the full transcription is copied to the clipboard automatically. Paste it anywhere with **Ctrl+V**.
- If a recording produces no audio (silent input, RMS below threshold, or very short utterance filtered by Whisper), **the clipboard and the text area are not overwritten**. The last successful transcription remains available for pasting.

### Audio feedback

A short chime plays when recording starts and again when it stops. This lets you minimize the window and work in another app — you will hear the state change without needing to watch the UI.

A dark-green audio-activity indicator in the top-right corner of the text area pulses while speech above the RMS threshold is detected.

---

## Model selection

The Whisper model is controlled by the `$MYTRANSCRIBE_MODEL` environment variable. This works on **both Linux and Windows** as of commit `832a697`.

### Available models

```
tiny   tiny.en   base   base.en   small   small.en
medium   medium.en   large-v1   large-v2   large-v3
large   large-v3-turbo   turbo
```

(`.en` variants are English-only; they are slightly faster and more accurate for English-only use.)

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

Open the shortcut's Properties, change the **Target** field to:

```batch
cmd /c "set MYTRANSCRIBE_MODEL=turbo && C:\path\to\MyTranscribe\run.bat"
```

### Defaults

| Platform | Default model | Rationale |
|---|---|---|
| Linux (`gui-v0.8.py`) | `small` | Original hardware sweet spot (NVIDIA 1660 Ti / 6 GB VRAM) |
| Windows (`gui_qt.py`) | `large-v3` | Tuned for the 4070 Ti Super (16 GB VRAM); falls back to CPU if CUDA is unavailable |

### Choosing a model

- **tiny / base** — Use on weak GPUs (≤4 GB VRAM) or when CPU fallback is your only option. Accuracy is lower; latency is minimal.
- **small / medium** — Balanced trade-off. `small` covers the tested 1660 Ti configuration. `medium` gives noticeably better accuracy if you have 5+ GB VRAM free.
- **large-v3** — Highest accuracy. Requires ~8–10 GB VRAM (measured 7–9 GB at fp16 on the 4070 Ti Super). Recommended if you have the hardware.
- **turbo** — A distilled large-v3 that is approximately 8× faster with a minor accuracy cost. Good choice when you want large-v3 quality on less VRAM (≈6 GB) or when transcription latency matters more than marginal accuracy.

---

## Troubleshooting

Full troubleshooting detail is in `docs/port-plan/05-install-runbook.md` §F. The items below cover the issues most likely to surface in a fresh install.

**`torch.cuda.is_available()` returns `False` (driver mismatch)**

Run `nvidia-smi` and check the driver version in the top-right corner. Drivers older than 528.xx will produce a silent CPU fallback or a `no kernel image` error. Update via GeForce Experience or [nvidia.com/drivers](https://www.nvidia.com/drivers). Also confirm that torch was installed from the pytorch.org wheel index (version string must end in `+cu124`, not just `2.6.0`).

**PyAudio cannot find the microphone (`-9996 Invalid input device`)**

On Windows, check **Settings → Privacy & security → Microphone** and confirm "Let apps access your microphone" is enabled. Also check **System → Sound → Input** to verify the device is not muted. If another app (Discord, Teams, Zoom) holds the microphone in exclusive mode, close it and retry. On Linux, run `arecord -l` to list ALSA capture devices; consult `System_dependencies.md` for ALSA/JACK guidance.

**`ffmpeg: FileNotFoundError`**

`ffmpeg` is not on the PATH that Python sees. Install it (`sudo apt-get install ffmpeg` on Ubuntu; `winget install Gyan.FFmpeg` on Windows) and verify with `ffmpeg -version` in a fresh terminal. On Windows, relaunch `run.bat` after the PATH change — existing consoles do not pick up the update automatically.

**Ctrl+Alt+Q global hotkey not firing**

On Windows, the four most common causes are: (1) antivirus/EDR blocking `pynput`'s low-level keyboard hook — check Windows Security → Protection History and add the project folder to Defender exclusions if flagged; (2) the foreground app is running elevated (Task Manager, regedit, "Run as administrator") — pynput running unelevated cannot intercept input directed at elevated windows, which is a documented Windows security boundary with no workaround short of also running MyTranscribe as admin; (3) another app (Google Meet in Chrome, some IDE plugins) has claimed Ctrl+Alt+Q; (4) Focus Assist (Do Not Disturb) is active. On Linux, note that pynput on Wayland requires the XWayland compatibility layer — if running a native Wayland session, switch to an X11 session or set `GDK_BACKEND=x11`.

**Transcription is silent despite speech (RMS threshold)**

If the app starts and stops without producing any text, the microphone signal may be below the RMS threshold of 80. The startup log will show an RMS line for each chunk — if the value is consistently below 80 on a quiet microphone, the threshold can be lowered in `transcriber_v12.py`. Also check that the correct input device is selected: the Windows device index can shift when USB devices are plugged or unplugged (see PyAudio troubleshooting above).

**DLL load error on Windows PyQt6 (`ImportError: DLL load failed`)**

PyQt6's Qt6 DLLs require the Microsoft Visual C++ 2015–2022 Redistributable (x64), which may be absent on a clean Windows install. Install it with:

```powershell
winget install Microsoft.VCRedist.2015+.x64
```

Then relaunch.

**OneDrive tempdir / `tempfile` path contains "OneDrive"**

If `%TEMP%` resolves to a OneDrive-synced path, Whisper's temporary audio files may trigger sync conflicts or permission errors. Verify with the audit script (`python scripts/audit.py`) or check C7 in `docs/port-plan/05-install-runbook.md`. Redirect `%TEMP%` to a local path in your shortcut's environment if needed.

---

## Project structure

```
MyTranscribe/
├── src/
│   ├── gui-v0.8.py              # Linux entry point (GTK3 / PyGObject)
│   ├── gui_qt.py                # Windows entry point (PyQt6)
│   ├── transcriber_v12.py       # Shared audio capture + Whisper backend
│   └── sound_utils.py           # Chime generator and player
├── scripts/
│   └── audit.py                 # Windows environment verification (12 checks)
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

The two entry points share `transcriber_v12.py` (audio recording, VAD, Whisper inference) and `sound_utils.py` (chime synthesis). All UI and hotkey code lives in the platform-specific entry point.

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

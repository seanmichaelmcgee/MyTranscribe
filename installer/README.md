# Windows installer (processor-only build)

Started 2026-11-19 so the app can be tried on a PC with no NVIDIA graphics card (for example a
laptop with integrated graphics), without installing Python.

## What the user gets

- **One file,** `MyTranscribe-Medical-Setup-<version>.exe`. Windows warns about it on first
  run ("Windows protected your PC"), because it is not code-signed. Choose **More info → Run
  anyway**.
- **Installs for that Windows account only,** into `%LOCALAPPDATA%\Programs\MyTranscribe
  Medical`, with no administrator rights. About 0.9 GB.
- **Adds:**
  - a desktop shortcut and a Start-menu shortcut, with the app icon;
  - an entry in Settings → Apps, for uninstalling.
- **At the end,** it offers to start the app. The first start opens the setup wizard.
- **Updating:** running a newer installer replaces the program files. Settings, word lists and
  the log (in `%APPDATA%\MyTranscribe` and `%LOCALAPPDATA%\MyTranscribe`) are kept.
- **Uninstalling** removes the program, the shortcuts and the Apps entry. Settings and word
  lists are removed only if the user ticks the box.
- **No internet is needed.** The speech model is inside the installer.

## What is inside

| Part | Details |
|---|---|
| `python\` | A private copy of Python 3.11. It is isolated by `python311._pth`, so nothing installed on the PC changes it. |
| `python\Lib\site-packages\` | Only the packages the app imports, and what they need. No NVIDIA libraries; unused parts of Qt removed. |
| `src\` | The app, exactly as in the repository. |
| `models\faster-whisper-small.en\` | The speech model for processor-only PCs. |
| `selftest.py` | `python\python.exe selftest.py` checks imports, picks the hardware, loads the model and decodes. |
| `THIRD-PARTY.txt` | Every bundled package and its declared licence. |

## How the processor-only setting was chosen (2026-11-19)

Speed was measured on four laptop-class processor cores: this PC's efficiency cores, pinned.
Accuracy was measured on the owner's 47 real recordings. A 5-year-old laptop is probably 1.5 to
2 times slower than these cores.

| Model | Wait after a 7.5 s message | Time for 30 s of speech | Word errors | Medical words wrong (of 314) |
|---|---|---|---|---|
| large-v3, on a graphics card (reference) | about 1 s | | 7.47% | 12 |
| medium.en | 10.4 s | 19.7 s | 8.78% | 16 |
| large-v3-turbo | 11.8 s | 14.7 s | | |
| distil-large-v3.5 | 11.3 s | 13.5 s | | |
| **small.en, 3 beams, patience 1** | **3.3 s** | **5.7 s** | **9.98%** | **36** |
| small.en, 5 beams, patience 2 (the GPU setting) | 4.8 s | 7.2 s | 9.98% | 36 |
| small.en, greedy | 3.1 s | 4.5 s | 10.48% | 43 |

- **Only small.en keeps up** with dictation on a laptop processor.
- **Search settings:** 3 beams with patience 1 keeps the accuracy of 5 beams with patience 2,
  but is much faster. With more than one beam, the vocabulary prompt is what costs time.
- **The accuracy cost is real.** The processor-only build makes about three times as many
  medical-word errors as large-v3 on a graphics card. The setup wizard says so.

## Building

Build with the app's development environment (the venv the tests use), on Windows:

```powershell
venv\Scripts\python.exe installer\make_icon.py          # only if the icon changes
venv\Scripts\python.exe installer\build_installer.py --model <folder>\faster-whisper-small.en --version 2026.11.19
```

- **It takes about 30 seconds and downloads nothing.** It copies this PC's Python and packages,
  and compiles `Setup.cs` with the C# compiler that is part of Windows (.NET Framework 4.8).
- **Output** goes to `dist\`, which is not in the repository.
- **The model folder** is a faster-whisper conversion from Hugging Face
  (`Systran/faster-whisper-small.en`, MIT).

**Scripted test** (no shortcuts; the setup log is `%TEMP%\MyTranscribe-setup.log`):

```powershell
dist\MyTranscribe-Medical-Setup-<version>.exe /S /noshortcuts "/D=C:\some\folder"
"C:\some\folder\Uninstall MyTranscribe.exe" /uninstall /S
```

## Before sharing beyond the owner

- **Code signing.** Without it, Windows SmartScreen warns every user, and managed PCs may block
  the file.
- **Licences of what is bundled.** `THIRD-PARTY.txt` lists them. PyQt6 is GPL v3 (or
  commercial), Qt is LGPL v3, PyAV includes FFmpeg (LGPL), and wordfreq's data is CC BY-SA
  4.0. Distributing them together needs a decision on the app's own licence terms.
- **Graphics acceleration on Intel, AMD and Apple hardware** is the next step for speed. See
  [../docs/CPU_AND_OTHER_HARDWARE_PLAN.md](../docs/CPU_AND_OTHER_HARDWARE_PLAN.md).

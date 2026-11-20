# Windows installer

Started 2026-11-19 so the app can be tried on a PC with no NVIDIA graphics card (for example a
laptop with integrated graphics), without installing Python. Since 2026-11-20 there is also a
[graphics-card edition](#graphics-card-edition-2026-11-20) with large-v3 for PCs with an NVIDIA
card. Without `--gpu` the build is the processor-only edition, as before.

## What the user gets

- **One file,** `MyTranscribe-Medical-Setup-<version>.exe` (`MyTranscribe-Medical-GPU-Setup-…`
  for the graphics-card edition; an installer past 4 GiB comes with a `.data` file that must stay
  beside it). Windows warns about it on first run ("Windows protected your PC"), because it is
  not code-signed. Choose **More info → Run anyway**.
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
| `python\Lib\site-packages\nvidia\cublas\bin\` | Graphics-card edition only: NVIDIA's cuBLAS, the one NVIDIA library Whisper loads on the card. |
| `src\` | The app, exactly as in the repository. |
| `models\faster-whisper-small.en\` | The speech model for processor-only PCs (`models\faster-whisper-large-v3\` in the graphics-card edition). |
| `selftest.py` | `python\python.exe selftest.py` checks imports, picks the hardware, loads the model and decodes; on the card it also checks that the NVIDIA libraries came from inside the install. |
| `THIRD-PARTY.txt` | Every bundled package and its declared licence, and the NVIDIA libraries' licence. |

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

**The real app, in real time, on the same four cores** (`scripts/live_app_trial.py`; the owner's
23 held-out recordings played through a virtual cable):
- **Wait after Stop:** median 3.6 s. Short messages took 3.0 to 3.8 s; long letters 5.5 to 9.3 s.
- **Word errors:** 5.88%. All 56 layout commands were kept.
- **Fix found on the way:** a piece that ended in silence was decoded a second time, which nearly
  doubled the wait after a long letter (11.7 s down to 6.6 s).

**Then, on the installed build itself** (2026.11.19 plus update 2026.11.19.3, its own Python and
model, same cores and recordings, 2026-11-19):
- **Short encoder windows:** a piece with up to 16 s of speech is encoded in a window of its
  speech plus 2 s instead of 30 s. The encoder costs the same for 3 s of speech as for 30, so
  this is most of the wait after a short message.
- **No second listen on the processor** for a dropped "new paragraph": a whole model pass each,
  and it recovered nothing on the owner's recordings.
- **Wait after Stop:** median 3.6 s -> 1.9 s. Short messages 3.0-3.8 s -> 1.3-2.1 s; long
  letters 5.5-10.5 s -> 4.3-7.5 s.
- **Accuracy:** word errors 5.58% -> 5.95% (live runs of one build vary by about 0.3); medical
  words wrong 16 -> 14 of 115; commands 55/56 and layout 11/12 both times.

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
  (`Systran/faster-whisper-small.en`, MIT). A `SOURCE.txt` in it is copied into
  `THIRD-PARTY.txt`.

**Graphics-card edition:** add `--gpu`, give large-v3 as the model, and put `--out` on a drive
with about 13 GB free (stage, zip and installer). It needs `nvidia-cublas-cu12` installed in the
venv, and takes about a minute.

```powershell
venv\Scripts\python.exe installer\build_installer.py --gpu --model <folder>\faster-whisper-large-v3 --version 2026.11.20 --out <folder>
```

**Scripted test** (no shortcuts; the setup log is `%TEMP%\MyTranscribe-setup.log`):

```powershell
dist\MyTranscribe-Medical-Setup-<version>.exe /S /noshortcuts "/D=C:\some\folder"
"C:\some\folder\Uninstall MyTranscribe.exe" /uninstall /S
```

## Update packages

A fix to the app's own code does not need the 0.7 GB installer again. An update package carries
only `src\` (about 0.6 MB) and works on a PC that already has the full install:

```powershell
venv\Scripts\python.exe installer\build_installer.py --update --version 2026.11.19.2
```

- **Same installer program, smaller payload.** Its window says "Update"; it replaces `src\`
  (putting the old one back if anything fails) and the version shown in Settings → Apps, and
  keeps Python, the packages, the speech model, the shortcuts and the user's settings.
- **It refuses** when nothing is installed, when the installed copy has a different Python, and
  while MyTranscribe is running.
- **The build refuses** when the packages here differ from the last full build (`dist\stage`),
  since an update cannot change them: build the full installer then.
- **Tested on this PC (2026-11-19):** full install, update refused while the app ran, silent
  update, update through its window, self-test of the updated copy, update refused without an
  install, uninstall.

## Graphics-card edition (2026-11-20)

`--gpu` builds the full-capability app (large-v3 on an NVIDIA card) as an installer, so it can
be tried the way a tester with an NVIDIA card would get it.

- **What it adds:** large-v3 (`Systran/faster-whisper-large-v3`, revision `edaa852e`, MIT: the
  snapshot the app has been validated with) and NVIDIA's cuBLAS 12.9 (`cublas64_12.dll`,
  `cublasLt64_12.dll`). How large-v3 decodes (beams, prompts, corrections, windows) is unchanged.
- **Size:** the 2026.11.20 installer is one file of 3.84 GB (3,836,451,496 bytes, SHA256
  `C5B8DAA997F6B75FE8AD586B79D7D472B426F0FF40DB3144E564F3E20339E1F2`); 4.3 GB installed.
- **Its own name, folder and Apps entry:** "MyTranscribe Medical (graphics card)", in
  `%LOCALAPPDATA%\Programs\MyTranscribe Medical (graphics card)`. It installs beside the
  processor-only edition and never updates, replaces or removes it; each edition's installer
  refuses a folder that holds the other. Settings, word lists and the log are shared by both.
- **Only what it carries is offered.** Options shows "Model: Whisper large-v3, on the graphics
  card" instead of Best/Fast, and the setup wizard does not ask; a saved "Fast" loads large-v3.

**How the contents were chosen:**
- **Only cuBLAS is needed.** large-v3 ran on an RTX 4070 Ti SUPER with the system CUDA removed
  from PATH, at int8_float16, float16, int8_float32 and float32, and the DLLs it loaded were
  listed. cuDNN (1.07 GB) and NVRTC (0.17 GB) were never loaded: CTranslate2 carries its own
  small cuDNN loader, which stays idle. Leaving them out keeps the installer at 3.8 GB, not 5.
- **Windows will not start a program file of 4 GiB or more.** A 4.43 GB test file was refused
  ("not a valid application for this OS platform"); a 4.29 GB one started. An installer that
  would pass the limit is therefore written as the program plus a `.data` file beside it, which
  the program finds by its recorded name. This build fits in one file.
- **Large zips:** the model (3.09 GB) lies past the 2 GB mark and needs zip64 records; the
  installer (.NET Framework 4.8) installed it in 10 seconds. A 4.6 GB test payload (program plus
  `.data`, files starting past 4.3 GiB) installed with every file byte-identical, and uninstalled.

**Tried on this desktop (2026-11-20),** installed to a folder on another drive, with no
`CUDA_PATH` and PATH set to Windows' own folders:
- **Self-test:** all pass: large-v3 from the install, on the card at int8_float16, with cuBLAS
  loaded from inside the install.
- **Speech:** a sentence made with Windows text-to-speech, through the installed app's engine,
  came out right ("metformin 500 mg twice daily … 130 over 80").
- **The app** logged the same model, device and compute type, also with "Fast" saved.
- **The processor-only copy** installed before kept its Apps entry and files, and still starts.

**Not decided yet:**
- **Cards with less than 5 GB** choose large-v3-turbo (under 3.5 GB, small.en), which this
  edition does not carry: the app asks before downloading it.
- **A PC with no usable card,** or a driver too old for CUDA 12, falls back to small.en on the
  processor and asks before downloading it (0.5 GB). Bundling small.en as well would take the
  installer past the one-file limit.
- **Drivers:** only this desktop's driver (616.64) has been tried.

## Before sharing beyond the owner

- **Code signing.** Without it, Windows SmartScreen warns every user, and managed PCs may block
  the file.
- **Licences of what is bundled.** `THIRD-PARTY.txt` lists them. PyQt6 is GPL v3 (or
  commercial), Qt is LGPL v3, PyAV includes FFmpeg (LGPL), and wordfreq's data is CC BY-SA
  4.0. Distributing them together needs a decision on the app's own licence terms.
- **NVIDIA's terms (graphics-card edition).** cuBLAS is under NVIDIA's CUDA Toolkit End User
  License Agreement, whose Attachment A lists the cuBLAS DLLs among the files that may be
  redistributed, under that agreement's conditions. Those conditions need checking before the
  graphics-card edition is shared beyond the owner. (The ctranslate2 package in both editions
  also carries NVIDIA's small cuDNN loader, `cudnn64_9.dll`.)
- **Graphics acceleration on Intel, AMD and Apple hardware** is the next step for speed. See
  [../docs/CPU_AND_OTHER_HARDWARE_PLAN.md](../docs/CPU_AND_OTHER_HARDWARE_PLAN.md).

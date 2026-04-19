# Meta-Plan: Assessing the MyTranscribe Linux→Windows Port Effort

## Context

MyTranscribe currently works on the user's Linux box. They want it running on their Windows machine for personal use only (no distribution). Same hardware, CUDA will be installed. The required functionality is unchanged: hotkey-triggered recording, Whisper transcription, automatic clipboard copy for `Ctrl+V` paste.

The user asked for a **meta-level plan** — i.e. how to *determine* the work involved, not the port itself. So this document lays out an investigation workflow and decision framework.

## Bottom-line preview (from initial survey)

The codebase is small (780 LOC across 3 files) and mostly platform-agnostic. The one real question is the GTK3 GUI: if GTK3/PyGObject can be made to run on Windows cheaply, the port is a few hours. If it cannot, swapping to a Windows-native toolkit (PyQt/PySide or Tkinter) is a ~1-day rewrite of `gui-v0.8.py`.

## Investigation dimensions (what to verify, in order)

### 1. Confirm the platform-sensitivity inventory

Already surveyed. Record for reference:

| Surface | File(s) | Platform risk |
|---|---|---|
| GTK3 + PyGObject GUI | `src/gui-v0.8.py` | **High** — the only real unknown |
| `Gtk.Clipboard` | `src/gui-v0.8.py:312-316` | Low — swap for `pyperclip` / `win32clipboard` if GTK goes |
| Global hotkeys via `pynput` | `src/gui-v0.8.py:84-87, 180-218` | Low — `pynput` is cross-platform; may need to run un-elevated |
| PyAudio (PortAudio) | `src/transcriber_v12.py`, `src/sound_utils.py` | Low — works on Windows; device enumeration differs |
| `openai-whisper` + `torch` + CUDA | `src/gui-v0.8.py:73-74`, `src/transcriber_v12.py:39-40, 187` | Low — first-class Windows support |
| Tempfile / path handling | `tempfile.gettempdir()`, `os.path.join` | None — already portable |
| Subprocess / shell | **none** | None |
| Config files | **none** | None |

Linux-specific artifacts (apt commands, `System_dependencies.md`) are documentation only — no code change needed.

### 2. Resolve the one open question: GTK3 on Windows

This is the branching factor. Two viable paths:

**Path A — Keep GTK3 via MSYS2 / GVSBuild.** PyGObject *does* run on Windows, typically via MSYS2's `mingw-w64-x86_64-python-gobject` or the GVSBuild artifacts. The setup is finicky (PATH, GI_TYPELIB_PATH, CSS rendering quirks) but requires zero code changes.

**Path B — Swap the GUI layer.** Rewrite `gui-v0.8.py` against PyQt6/PySide6 or Tkinter. Re-implements ~200 LOC of window + CSS + clipboard. `transcriber_v12.py` and `sound_utils.py` stay untouched.

**How to decide between A and B, cheaply:**
1. Spin up a fresh Python venv on the Windows box.
2. Try `pip install PyGObject` (Windows wheels are available as of 2024+); if that fails, try the MSYS2 route.
3. Run the absolute minimum smoke test: `python -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk; Gtk.Window().show_all()"`.
4. If it pops a window within ~30 min of fiddling → Path A. If not → Path B.

Time-box this step to **1 hour**. Don't sink a day into MSYS2 if it's fighting you — Path B is bounded work.

### 3. Validate the ML stack independently of the GUI

Before touching the GUI question, confirm the heavy stuff works. These are known quantities but worth a 10-minute sanity check:

1. Install CUDA Toolkit (matching the torch build — e.g. CUDA 12.1 for torch 2.6).
2. `pip install torch --index-url https://download.pytorch.org/whl/cu121` (adjust index for chosen CUDA).
3. `python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"`.
4. `pip install openai-whisper` and load the `small` model once to populate the cache (Windows cache path: `%USERPROFILE%\.cache\whisper` — handled by the library).

If this works, items 5-6 of the original inventory are closed.

### 4. Validate audio + hotkeys

1. `pip install pyaudio` (prebuilt wheel exists for Windows Python 3.10–3.12; if it fails, install from the Gohlke-style wheel or use `pipwin`).
2. List input devices and confirm the intended mic is present.
3. `pip install pynput` and run a 10-line listener script to verify `Ctrl+Alt` combo detection works when the script is **not** run as admin. (Some games / elevated windows block pynput — not an issue for this use case.)

### 5. Decide the port shape and write the real implementation plan

After steps 2–4, the effort estimate falls into one of three buckets:

| Scenario | Code changes | Setup time | Total effort |
|---|---|---|---|
| Path A works | None (maybe 5-line clipboard fallback) | 1–3 hrs (MSYS2 + CUDA + deps) | **Half a day** |
| Path B, PyQt swap | ~200 LOC rewrite of `gui-v0.8.py` only | 1–2 hrs deps | **~1 day** |
| Path B, Tkinter swap | ~150 LOC rewrite, uglier UI but zero extra deps | 1 hr deps | **~1 day** |

Once a bucket is chosen, *that's* when the detailed implementation plan gets written — not before.

## Files that matter

- `src/gui-v0.8.py` — the only file likely to change
- `src/transcriber_v12.py` — leave alone
- `src/sound_utils.py` — leave alone
- `requirements.txt` — will need a Windows-targeted variant (torch+cu121 index, maybe drop PyGObject if going Path B)
- `System_dependencies.md` — add a Windows section; keep the Ubuntu one

## Verification / end-to-end test (applies to either path)

1. Launch the app; window appears, stays on top.
2. Hold `Ctrl+Alt` → recording chime plays, status indicator goes red.
3. Speak a short sentence, release → transcription chime plays, text appears in the status area.
4. Focus any text field in another app, press `Ctrl+V` → transcribed text pastes.
5. `Ctrl+Alt+Q` exits cleanly.
6. Confirm in Task Manager that GPU is engaged during transcription (or check `torch.cuda.is_available()` log line).

If all six pass, the port is done.

## What to do in the new Windows session

Tell Claude which path to investigate first — the conservative "try to keep GTK3" (Path A) or the pragmatic "just rewrite the GUI in PyQt/Tkinter" (Path B). Recommendation: try A for 1 hour, then cut to B if MSYS2 gets ugly.

# MyTranscribe Windows Port — Architecture & Phasing Plan

**Branch:** `claude/windows-port-pyqt6`
**Target:** Windows 11, RTX 4070 Ti Super, Python 3.11.9, personal use only
**Strategy:** Path B — keep `transcriber_v12.py` + `sound_utils.py` intact; rewrite `gui-v0.8.py` in PyQt6.
**Design principle:** every phase ends in a fast, localized smoke test so a regression is provably in the work just done — not in an earlier layer.

---

## 1. Phase breakdown

### Phase 0 — Environment snapshot & pin
**Goal:** Freeze the known-good interpreter state so later regressions can be diffed against a baseline.

- **Entry criteria:** Source tree present at `C:/Users/smich/Apps/MyTranscribe`; branch `claude/windows-port-pyqt6` checked out; Python 3.11.9, torch 2.6.0+cu124, whisper, PyAudio, pynput already installed (per context).
- **Exit criteria:**
  - `pip freeze > docs/port-plan/env-baseline.txt` committed (sans the commit itself — captured now, committed at end).
  - `python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` prints `True <device>`.
  - `python -c "import pyaudio, pynput, whisper; print('ok')"` prints `ok`.
  - `ffmpeg -version` prints a version line.
- **Rollback point:** N/A — read-only phase. On failure, stop and ask the user to repair the environment.
- **Wall-clock:** 10 min.

### Phase 1 — Transcriber hardening (the one agreed code change)
**Goal:** Apply the single pre-approved fix to `transcriber_v12.py:221-222` so a stale-file delete on Windows cannot crash the audio loop.

- **Entry criteria:** Phase 0 complete.
- **Exit criteria:**
  - `os.remove(wav_filename)` is wrapped in `try/except OSError` (logged at DEBUG).
  - New file `tests/smoke_transcriber.py` (or inline throwaway) loads the `tiny` model, records 3 s of silence, and exits without raising. No clipboard, no GUI, no hotkey — just the backend.
  - Smoke exits 0 and logs `GPU acceleration is enabled.`
- **Rollback point:** `git checkout -- src/transcriber_v12.py` returns to pre-phase state; no other file touched.
- **Wall-clock:** 20 min.

### Phase 2 — PyQt6 install & minimal scaffold
**Goal:** Prove PyQt6 paints a window on this machine, independent of any app logic.

- **Entry criteria:** Phase 1 complete.
- **Exit criteria:**
  - `pip install PyQt6` succeeds; `pip show PyQt6` prints a version.
  - A 30-line `src/gui_qt_scaffold.py` (throwaway) opens a frameless-friendly `QMainWindow` with a `QTextEdit` + 3 `QPushButton`s (Start / Long / Stop), Always-on-Top flag set, 0.9 opacity. Closing the window exits the process cleanly.
  - No import of `transcriber_v12`, `pynput`, or `sound_utils` yet.
- **Rollback point:** Delete `src/gui_qt_scaffold.py`; `pip uninstall PyQt6` if install itself was the problem. No source file touched.
- **Wall-clock:** 30 min.

### Phase 3 — Feature parity rewrite (`src/gui_qt.py`)
**Goal:** Port every behavior of `gui-v0.8.py` into a single PyQt6 module, wired to the real transcriber and chime player but **without** the global hotkey yet.

- **Entry criteria:** Phase 2 scaffold ran.
- **Exit criteria:** All of the following work by mouse/keyboard inside the window:
  - Start button → chime plays, `transcriber.start_recording("normal")` runs in its existing background thread, a `QTimer(30ms)` drives the text update + audio indicator show/hide.
  - Long Record button → same, mode="long", text area shows `"Recording in long mode..."`.
  - Stop button → end chime, `force_process_partial_frames()` + `stop_recording()`, final text is written to the `QTextEdit`, `QApplication.clipboard().setText(final_text)` sets the clipboard, Ctrl+V pastes it into Notepad.
  - Spacebar inside the window toggles normal-mode start/stop.
  - Button sensitivity flips correctly (Start/Long disabled while recording, Stop enabled).
  - Window stays on top, 0.9 opacity, title "Real-Time Transcription", default size ~650x200.
  - Closing the window shuts down `ChimePlayer.cleanup()` and exits.
- **Rollback point:** All work is in the new file `src/gui_qt.py`. Delete it to return to a working Phase-2 state. `gui-v0.8.py` is untouched and still on disk.
- **Wall-clock:** 2.5 hrs.

### Phase 4 — Global hotkey integration (Ctrl+Alt+Q)
**Goal:** Re-attach `pynput` global hotkey so the app can be triggered when unfocused — the riskiest cross-thread boundary.

- **Entry criteria:** Phase 3 fully smoke-tested.
- **Exit criteria:**
  - `pynput.keyboard.Listener` started from `gui_qt.py`.
  - Hotkey callback dispatches to the GUI thread via `QMetaObject.invokeMethod(..., Qt.ConnectionType.QueuedConnection)` **or** a pre-wired `pyqtSignal` (pick one; signal is simpler — use that). No direct widget calls from the pynput thread.
  - With focus on Notepad, pressing Ctrl+Alt+Q starts recording (chime audible, app window does not need to steal focus but `self.raise_()` / `activateWindow()` may be called). Releasing the combo and pressing Ctrl+Alt+Q again stops it, clipboard is populated, Ctrl+V into Notepad pastes the transcript.
  - No crashes from the listener thread on app exit (listener is `.stop()`-ed in the Qt `closeEvent`).
- **Rollback point:** Revert the single commit from this phase (kept small intentionally); Phase 3 build still works hotkey-less.
- **Wall-clock:** 1 hr.

### Phase 5 — End-to-end verification & launcher polish
**Goal:** Run the six-step verification from `WINDOWS_PORT_PLAN.md` §"Verification / end-to-end test" and add a one-click launcher.

- **Entry criteria:** Phase 4 complete.
- **Exit criteria:**
  - All six verification steps pass (window, hotkey recording, speech transcription, clipboard paste, Ctrl+Alt+Q exit/stop, GPU engaged — checked via Task Manager GPU graph or the existing `GPU acceleration is enabled` log line).
  - `run_windows.bat` (or `run_windows.ps1`) at repo root activates the venv (if any) and runs `python src/gui_qt.py`.
  - `requirements-windows.txt` generated from `pip freeze` of the *actually used* packages (PyQt6, pynput, pyaudio, numpy, torch, openai-whisper). PyGObject intentionally absent.
  - A short `docs/port-plan/99-verification-log.md` records each of the six steps with pass/fail.
- **Rollback point:** N/A — if verification fails we re-enter Phase 3 or 4 depending on symptom. Do not mutate `main` or merge.
- **Wall-clock:** 45 min.

**Total estimated wall-clock: ~5 hrs 15 min** (plus slack for the two checkpoints).

---

## 2. Dependency graph

```
Phase 0  ──▶  Phase 1  ──▶  Phase 2  ──▶  Phase 3  ──▶  Phase 4  ──▶  Phase 5
                                             │
                                             └──▶ (cut point A: usable app, no global hotkey)

                                                             │
                                                             └──▶ (cut point B: full app, formal verification deferred)
```

- **Phase 0 → 1:** needs a working torch/CUDA to smoke-test the transcriber.
- **Phase 1 → 2:** independent in principle, but we want Phase 1 proven first so any later transcriber misbehavior is definitely not our `os.remove` edit.
- **Phase 2 → 3:** Phase 3 imports nothing PyQt6-specific that Phase 2 hasn't already loaded successfully.
- **Phase 3 → 4:** Phase 4 only adds a thread-safe signal emitter; everything it calls already works from buttons.
- **Phase 4 → 5:** verification is strictly downstream.

### Cut points (useful partial results)

- **Cut point A — after Phase 3.** A fully functional GUI app usable via mouse + spacebar. No global hotkey, but speech → clipboard works. This is already a 90% win for the user's actual use case if they want to stop here.
- **Cut point B — after Phase 4.** Full feature parity with Linux. Phase 5 is polish (launcher `.bat`, pinned requirements, formal checklist) and can be skipped or deferred.

---

## 3. Parallelizable work

- **Draft the Phase 5 verification checklist (`docs/port-plan/99-verification-log.md` stub) during Phase 3.** Zero code risk, no source-file overlap. Writing the checklist often exposes missing Phase 3 behavior before it ships. *Can parallelize with Phase 3.*
- **Write `requirements-windows.txt` skeleton (just the names, no pins) during Phase 2.** Pin versions at end of Phase 5. *Can parallelize with Phase 2.*
- **Write `run_windows.bat` during Phase 4** — it only needs to know the final entry-point filename (`src/gui_qt.py`), which is fixed from Phase 3 onward. *Can parallelize with Phase 4.*
- **Document the three integration risks (section 4 below) as inline `# RISK:` comments at the exact call sites in Phase 3.** Surfaces them for Phase 4 debugging without any extra file. *Can parallelize with Phase 3.*

What CANNOT be parallelized: Phases 3 and 4 share the same file (`src/gui_qt.py`). Do not split them across concurrent workers.

---

## 4. Top 3 integration risks

### Risk A — Cross-thread GUI mutation from pynput listener
**Description:** `pynput`'s `Listener` callback fires on its own OS thread; calling `QTextEdit.setText` or `QPushButton.setEnabled` directly from there will intermittently crash with "QObject::setParent: Cannot set parent, new parent is in a different thread" or silently wedge the event loop.
**Surfaces in:** Phase 4.
**Mitigation:** In Phase 3, define a `class HotkeyBridge(QObject)` with a `pyqtSignal(str)` emitted for `toggle`. In Phase 4, the pynput callback only calls `self.bridge.toggle.emit("toggle")`. The connected slot runs on the GUI thread by default (auto-connection is `QueuedConnection` across threads). Zero direct widget calls from the listener thread.

### Risk B — Clipboard write races hotkey release
**Description:** On Windows, `QClipboard.setText()` performed while the user is still holding Ctrl+Alt (the release edge hasn't fired yet) occasionally loses the write, because the OS clipboard owner is contested during modifier-release. Linux GTK masks this with `clipboard.store()`; PyQt6 has no equivalent synchronous-flush API.
**Surfaces in:** Phase 4 (never reproduces in Phase 3 because buttons are clicked, not hotkey-toggled).
**Mitigation:** In the hotkey-driven stop path, schedule the clipboard write with `QTimer.singleShot(150, lambda: clip.setText(final_text))`. 150 ms is well past any plausible modifier-release; imperceptible to a human hitting Ctrl+V afterward. Button-driven stop keeps the immediate write.

### Risk C — QTimer(30ms) granularity vs Whisper GPU blast
**Description:** The original GTK code uses `GLib.timeout_add(30, ...)` for the audio-indicator/text-refresh tick. During a Whisper inference call on CUDA, the Python thread is blocked in the C extension for 100–800 ms; Qt's event loop on Windows has been observed to coalesce pending 30 ms timer ticks into a single burst afterward, producing a visually stuttery indicator. Benign but visible.
**Surfaces in:** Phase 3 during the first real speech test; gets worse in Phase 5 under a long-record transcript.
**Mitigation:** Leave the 30 ms timer. If stutter is objectionable, move the indicator poll to a 50 ms `QTimer` driven by `transcriber.audio_detected` only — do not re-render the full `QTextEdit` every 30 ms. Update text on a slower 150 ms cadence. Cheap fix, kept in reserve; do not pre-optimize.

---

## 5. Go/no-go checkpoints

### Checkpoint 1 — after Phase 2 (before any real app logic in Qt)
**Why stop here:** This is the last point where the only installed net-new dependency is PyQt6 and the only new file is a throwaway scaffold. If the scaffold window doesn't appear, or if PyQt6 has a subtle DPI/Wayland-equivalent glitch on this specific Windows install, it's far cheaper to diagnose now than after 2.5 hrs of Phase 3 work is layered on top.
**Ask the user:** "PyQt6 scaffold window opened, always-on-top + 0.9 opacity both work. Proceed to the full rewrite?"

### Checkpoint 2 — after Phase 3, before Phase 4
**Why stop here:** Phase 3 gives cut point A — a fully working app minus the global hotkey. Phase 4 is the riskiest phase (cross-thread + clipboard timing + listener shutdown ordering). The user may decide the button/spacebar UX is sufficient and defer Phase 4, or may want to manually smoke-test Phase 3 under their real workload before we touch the threading model.
**Ask the user:** "Mouse/spacebar recording, transcription, and clipboard paste all work. Ready to wire up Ctrl+Alt+Q global hotkey (adds pynput ↔ Qt thread bridge)?"

---

## Appendix — files that will be created by this plan

| File | Created in phase | Kept? |
|---|---|---|
| `docs/port-plan/01-architecture.md` | (this doc) | yes |
| `docs/port-plan/env-baseline.txt` | 0 | yes |
| `tests/smoke_transcriber.py` | 1 | optional (throwaway OK) |
| `src/gui_qt_scaffold.py` | 2 | **no** — delete before Phase 3 commit |
| `src/gui_qt.py` | 3 | yes — the new entry point |
| `docs/port-plan/99-verification-log.md` | 3 (stub) / 5 (filled) | yes |
| `requirements-windows.txt` | 5 | yes |
| `run_windows.bat` | 5 | yes |

Files **never** modified by this plan: `src/gui-v0.8.py`, `src/sound_utils.py`, `requirements.txt`, `System_dependencies.md`.
Files modified exactly once: `src/transcriber_v12.py` (the 2-line `os.remove` guard, Phase 1).

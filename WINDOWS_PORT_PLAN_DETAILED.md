# Detailed Windows Port Plan — PyQt6

This is the synthesized, implementation-ready plan for porting MyTranscribe (GTK3/Linux → PyQt6/Windows). It supersedes the meta-plan in [WINDOWS_PORT_PLAN.md](WINDOWS_PORT_PLAN.md) by resolving its open questions and producing concrete artifacts.

## Decision summary

- **Path A (keep GTK3 on Windows): rejected.** PyGObject ships source-only on PyPI; `pip install PyGObject==3.50.0` fails on Windows without a full Visual Studio build environment. The gvsbuild zip route works but requires unpinning PyGObject and non-standard wheel installs — the 1-hour time-box from the meta-plan would be consumed entirely by environment plumbing.
- **Path B with PyQt6 (not Tkinter): chosen.** ~130 LOC rewrite of `gui-v0.8.py` only. PyQt6 maps 1:1 for every GTK call the app uses (`set_keep_above`, `set_opacity`, CSS border-radius, `GLib.timeout_add`, `Gtk.Clipboard`). Tkinter would be ~170 LOC with worse styling fidelity.
- **Scope**: `src/gui_qt.py` (new, ~230 LOC) + 4-line hardening patch in `src/transcriber_v12.py`. `src/sound_utils.py` untouched. `requirements-windows.txt`, `run.bat`, `scripts/audit.py` added.
- **Total estimated wall-clock**: ~5 hr 15 min across 6 phases.

## Plan documents (read in order)

| # | Document | What it is |
|---|---|---|
| 0 | [WINDOWS_PORT_PLAN.md](WINDOWS_PORT_PLAN.md) | Original meta-plan — investigation framework |
| 1 | [docs/port-plan/01-architecture.md](docs/port-plan/01-architecture.md) | 6-phase breakdown with entry/exit/rollback criteria and 2 go/no-go checkpoints |
| 2 | [docs/port-plan/02-ux-contract.md](docs/port-plan/02-ux-contract.md) | Behavioral spec — 60 MUST, 5 SHOULD, 7 MAY-drop items |
| 3 | [docs/port-plan/03-risk-verification.md](docs/port-plan/03-risk-verification.md) | 36-risk register + 26 test cases (T00–T25) |
| 4 | [docs/port-plan/04-pyqt6-impl-spec.md](docs/port-plan/04-pyqt6-impl-spec.md) | Line-level spec for `src/gui_qt.py` — classes, signals, QSS, state machine |
| 5 | [docs/port-plan/05-install-runbook.md](docs/port-plan/05-install-runbook.md) | Copy-paste install commands, troubleshooting, uninstall |
| 6 | [docs/port-plan/06-verification-executable.md](docs/port-plan/06-verification-executable.md) | Phase-to-test mapping + runnable test recipes + triage flowchart |

## Phase overview

| Phase | Goal | Time | Rollback point |
|---|---|---|---|
| 0 | Environment snapshot & pin | 10 min | n/a |
| 1 | Transcriber hardening (`os.remove` guard) | 20 min | revert single file |
| 2 | PyQt6 install + throwaway scaffold window | 30 min | delete scaffold |
| 3 | Feature-parity rewrite → `src/gui_qt.py`, no global hotkey yet | 2.5 hrs | delete `gui_qt.py` |
| 4 | `pynput` global hotkey via `pyqtSignal` bridge | 1 hr | remove HotkeyBridge class |
| 5 | E2E verification + `run.bat` + final `requirements-windows.txt` | 45 min | n/a |

**Phases 0, 1, 2, 5 are largely DONE** as part of the planning work — the venv exists with torch+CUDA+whisper+PyQt6 all validated, `requirements-windows.txt` is finalized, `run.bat` exists, `scripts/audit.py` passes 12/12 on the target machine, and the transcriber `os.remove` guard has been applied. **Phases 3 and 4 are the remaining implementation work.**

## Go/no-go checkpoints

1. **After Phase 2** (PyQt6 scaffold): confirm always-on-top + 0.9 opacity render correctly on *this* Windows install before investing in the full rewrite. Status: scaffold smoke test already passed during install-runbook agent work — green.
2. **After Phase 3, before Phase 4** (full mouse/spacebar app + clipboard paste verified): confirm before wiring the riskiest piece — cross-thread `pynput`↔Qt bridge + clipboard-vs-modifier-release timing.

## High-risk items to watch

From [risk-verification.md](docs/port-plan/03-risk-verification.md) — the four H×H risks:

- **R01** — PyAudio default picks wrong input device on Windows. *Mitigation*: surface mic selection on first run; T11 verifies.
- **R08** — `QApplication.clipboard().setText()` called from a non-GUI thread. *Mitigation*: route all clipboard writes through a `pyqtSignal(str)` with `QueuedConnection`.
- **R23** — PyQt6 signal/slot cross-thread misuse (replaces `GLib.idle_add`). *Mitigation*: daemon pynput listener emits only the signal; connection type is `QueuedConnection`.
- **R25** — Whisper worker thread touching Qt widgets directly. *Mitigation*: Whisper thread emits `result_ready = pyqtSignal(str)`, widget mutation happens on the slot.

## Top non-obvious contract items

From [ux-contract.md](docs/port-plan/02-ux-contract.md) — things an implementer reading a naive spec would break:

- **Ctrl+Alt+Q and Spacebar are no-ops in long-recording mode** — not a toggle, not a stop. This falls out of GTK3 conditions that happen to be false during long mode; must be preserved explicitly in PyQt6.
- **No auto-transition when the 180 s long-mode backend timeout fires** — GUI stays in `LongRecording` until user hits Stop.
- **30 ms GUI polling cadence is intentional** — audio-indicator feel; do not slow it.
- **Native Windows title bar replaces the custom HeaderBar** — the one intentional visual deviation from Linux.

## One known implementation risk flagged by the impl-spec agent

`_audio_indicator` is a child `QFrame` of `self._text_area.viewport()` manually repositioned via `_reposition_indicator()`. The spec uses `resizeEvent` on the main window, but `QTextEdit` relays resize events to its viewport in a non-obvious way. **Smoke-test the indicator early in Phase 3** — if it jumps or disappears on resize, override `resizeEvent` on the viewport widget itself.

## Triage suite (run after every implementation checkpoint, ~90 seconds)

1. `./venv/Scripts/python.exe scripts/audit.py` — 12 checks, ~5 s
2. **T02** — CUDA smoke: model loads on GPU, 1-frame inference succeeds, ~15 s
3. **T05+T06** — Ctrl+Alt+Q from focused Notepad → chime → clipboard → Ctrl+V paste, ~45 s end-to-end

See [06-verification-executable.md §C](docs/port-plan/06-verification-executable.md).

## What's NOT in scope

- Distribution / installer / PyInstaller packaging
- Multi-user or admin-elevated support
- Auto-start on login
- Fine-tuning Whisper, additional languages, post-processing
- Any change to `src/sound_utils.py` beyond what's already there

## Environment already validated on target machine

- Python 3.11.9 at `C:/Users/smich/AppData/Local/Programs/Python/Python311/python.exe`
- ffmpeg 8.0 on PATH
- NVIDIA RTX 4070 Ti Super, driver 591.74, CUDA 12.4 via `torch 2.6.0+cu124`
- venv at `venv/` with torch, whisper (tiny loaded on CUDA), PyAudio (13 input devices enumerated), pynput, PyQt6 6.11.0
- `scripts/audit.py` exits 0, all 12 checks PASS

## Next action

Green-light Phase 3 (feature-parity rewrite → `src/gui_qt.py`). Estimated 2.5 hours. Cut point after Phase 3 provides a fully usable app minus global hotkey.

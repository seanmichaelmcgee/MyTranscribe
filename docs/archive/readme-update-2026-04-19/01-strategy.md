# README Rewrite Strategy — MyTranscribe

**Branch:** `claude/windows-port-pyqt6`
**Date:** 2026-04-19
**Scope:** Strategy only. No README prose in this document.

This plan guides a thorough rewrite of `README.md` now that the repo ships two
first-class desktop entry points: `src/gui-v0.8.py` (GTK3/Linux) and
`src/gui_qt.py` (PyQt6/Windows). The current README is Linux-only, pre-port,
and contains stale "Future Development" material that never shipped.

---

## 1. Target audience & scope

The README is for the repo owner (future self, ~6 months from now, forgetting
which venv steps mattered) and any friend or collaborator the owner hands the
repo link to — someone technical enough to run Python from a terminal but not
necessarily familiar with either GTK or Qt, and who may be on Linux **or**
Windows without prior preference.

It is **not** a developer contribution guide, **not** a doc site, and **not**
a marketing page. It does not document architecture (the `docs/port-plan/`
suite covers that), does not walk through code internals, and does not replace
`System_dependencies.md` or `docs/port-plan/05-install-runbook.md` — it points
to them.

---

## 2. Section outline of the new README

Proposed top-to-bottom structure, 13 sections. Each entry: purpose, target
length, and which source docs inform it.

| # | Section | Purpose (1 sentence) | Target length | Source docs |
|---|---|---|---|---|
| 1 | Title + one-line tagline + badges | Identify the project; keep the existing version/python/license badges refreshed to 0.10 + 3.11. | ~5 lines | existing README lines 1–7 |
| 2 | Overview | Explain what the app does, set the "optimized for English" expectation, and note the honest iterative-LLM-assisted provenance. | ~150 words | existing README §Overview; `02-ux-contract.md` |
| 3 | Features | Bullet list of user-visible capabilities (real-time transcription, two recording modes, global hotkey, clipboard auto-copy, always-on-top minimal UI, audio chime feedback, CPU fallback). | ~10 bullets, ≤120 words | existing README §Features; `02-ux-contract.md` MUST items |
| 4 | Hardware expectations | Per-model VRAM guidance + the two tested configs (1660 Ti 6GB with "small"; 4070 Ti Super with "large-v3") + note on CPU fallback being functional but slow. | ~120 words + small table | existing README lines 15–20; `05-install-runbook.md` §A; `gui_qt.py` constants |
| 5 | Installation — Linux | Short happy-path (venv + requirements.txt + apt-get system deps), with a pointer to `System_dependencies.md` for the full apt/brew list and ALSA/JACK troubleshooting. | ~60 lines incl. code blocks | existing README §Installation; `System_dependencies.md` |
| 6 | Installation — Windows | Short happy-path (Python 3.11 + torch-cu124 + requirements-windows.txt + `--no-build-isolation` note), with a pointer to `docs/port-plan/05-install-runbook.md` §A–C for the full runbook. | ~70 lines incl. code blocks | `05-install-runbook.md` §A–C |
| 7 | First run + model download | Explain the one-time Whisper model download (~2.9 GB for large-v3, cached to `~/.cache/whisper`), the 5–10 s CUDA warmup on first Start (documented non-blocker from `07-human-verification.md` §D.1), and what a healthy startup log looks like. | ~80 words | `07-human-verification.md` §D; `gui_qt.py` startup logging |
| 8 | Launch workflows | Document the primary recommendation per OS + a brief mention of alternatives — see §3 of this strategy doc. | ~100 words per OS | see §3 below |
| 9 | Usage — controls | Mouse buttons (Start / Stop / Long Record) + Spacebar (window-focused) + Ctrl+Alt+Q (global), with a **clearly flagged** subsection explaining the long-recording no-op contract (Space and Ctrl+Alt+Q are deliberately inert while long-recording is active — press Stop to end it). | ~80 words incl. the no-op callout | existing README §Controls; `02-ux-contract.md`; `07-human-verification.md` HT-05 |
| 10 | Model selection | Document `$MYTRANSCRIBE_MODEL` env var, available values (tiny/base/small/medium/large-v3/turbo), and the VRAM trade-off. Note: the Windows entry point supports the env var; the Linux `gui-v0.8.py` currently has a hardcoded "small" (document this honestly — do not overclaim parity). | ~70 words | `gui_qt.py` lines 67–70, 331–341, 648–655; `gui-v0.8.py` line 74 |
| 11 | Troubleshooting | Top 5–8 issues distilled from `05-install-runbook.md` §F: CUDA not available, PyAudio device errors, PyQt6 VCRedist DLL error, pynput hotkey blocked by AV, elevated-app hotkey swallowing, ffmpeg missing, OneDrive tempdir, and (Linux) ALSA/JACK pointer. | ~150 words | `05-install-runbook.md` §F; `System_dependencies.md` §ALSA/JACK |
| 12 | Project structure | Brief tree showing `src/gui-v0.8.py`, `src/gui_qt.py`, `src/transcriber_v12.py`, `src/sound_utils.py`, `scripts/audit.py`, `run.bat`, `docs/port-plan/`. No per-class internals. | ~15 lines | existing README §Project Structure; repo root listing |
| 13 | License + acknowledgements | Carry forward. Add PyQt6/Qt to the acknowledgements list alongside GTK. | ~10 lines | existing README §License + §Acknowledgements |

**Total target length:** roughly 350–450 lines of Markdown, comparable to the
existing README but with much more going on per line.

---

## 3. Two workflow recommendations

### 3.1 Linux launch workflow — primary: **bash alias in `~/.bashrc`**

Recommend the bash alias the user is already using. The repo is a personal
tool; contributors are rare and technical; the alias is one line, lives
entirely outside the repo (so it won't be clobbered by `git pull`), gives a
fast terminal-friendly launch, and needs zero install tooling. The README
should show the exact alias form (with the `cd && source venv/bin/activate &&
python src/gui-v0.8.py` chain the user already runs) and the
`source ~/.bashrc` refresh step.

**Briefly mention** the `.desktop` file as an alternative for users who live
in GNOME/KDE Activities and prefer launching from the Super key — keep that to
one sentence pointing at the snippet the current README already has (salvage
that block, do not drop it entirely). **Do not** recommend a `bin/` wrapper
script installed via `ln -s` — that adds repo-internal complexity the user
has explicitly not asked for.

### 3.2 Windows launch workflow — primary: **Windows shortcut (.lnk) to `run.bat`**

Recommend what the user asked for. `run.bat` already exists, already handles
`cd /d "%~dp0"` so the shortcut's "Start in" field is irrelevant (mitigates
risk R15 from the port plan), and a `.lnk` on the Desktop or pinned to the
Start Menu is the idiomatic Windows launch pattern. The README should give
step-by-step instructions: right-click `run.bat` → Create shortcut → move to
Desktop (or `%APPDATA%\Microsoft\Windows\Start Menu\Programs\` for the Start
Menu), optionally set a custom icon, optionally set "Run: Minimized" so the
console window is unobtrusive.

**Briefly mention** a PowerShell function in `$PROFILE` as a terminal-friendly
alternative that mirrors the Linux alias pattern, for users who prefer
keyboard launches. **Do not** recommend PyInstaller (scope expansion — the
user hasn't asked) or Task Scheduler (overkill for personal use).

---

## 4. What to carry forward from the existing README

**Preserve (verbatim or lightly edited):**

- The one-line tagline and badges (update version to 0.10 and Python to 3.11).
- The "optimized for English" caveat from §Overview — this is an honest,
  important limitation.
- The hardware configuration sentences (1660 Ti / 4070 Ti tested configs) —
  move into the Hardware section.
- The LLM-assisted provenance sentence ("built primarily using iterative
  work on consumer-level LLMs…") — keep, move into Overview.
- The green-status-bar / audio-chime feedback sentence — move into Usage.
- The DEFAULT_CHUNK_DURATION / 300 s / 180 s tuning note — trim, keep the
  sense, move into Features or a small "Tuning" footnote.
- The per-model VRAM table (tiny/base/small/medium/large with VRAM figures)
  — move into Hardware, add "large-v3" and "turbo" entries, correct
  "10 GB" → "~10 GB, measured 7–9 GB for large-v3 at fp16" if the owner
  can verify on the 4070 Ti Super.
- The `.desktop` file snippet — keep as the Linux secondary option
  (§3.1 above).
- The full §License and §Acknowledgements sections — carry over, add PyQt6
  + Qt, add pynput.

**Drop outright:**

- **§Future Development → Docker Containerization (lines 181–199).** Grep of
  `git log` for "docker" (all branches, all commits, case-insensitive)
  returns zero results. The user never picked this up; nineteen months on,
  it is not a plan, it is aspirational fiction. Remove the section entirely,
  not even as a "maybe someday" footnote.
- **§Other Planned Improvements (lines 193–198).** Same reasoning — these
  are year-old aspirations with no commits against them. Drop.
- **§Distribution (lines 200–204).** The ONNX speculation has not been
  acted on. Drop. The "run from a terminal within a virtual environment"
  guidance is covered better by §Launch workflows in the new structure.
- **§Customization → Changing Whisper Model Size code-edit instructions
  (lines 148–163).** On the Windows entry point this is obsoleted by
  `$MYTRANSCRIBE_MODEL`; on the Linux entry point the hardcoded line is
  trivia. Mention editing line 74 of `gui-v0.8.py` in one sentence in the
  Model Selection section, don't dedicate a subsection to it.
- **§Customization → Modifying Recording Duration (lines 164–179).** Same
  reasoning — code-edit instructions with line numbers belong in a
  contributor guide, not a user-facing README. One sentence pointing to
  the two tunable constants in `transcriber_v12.py` is enough.

**One additional recommendation for the user to review:** the
`🔍 / ✨ / 🛠️ / 🚀 / 🏗️ / 🔮 / 📜 / 🙏` section emojis in the current README
are noisy; the owner has not indicated a preference. Recommend dropping
them for a cleaner cross-platform read, but flag as stylistic — not a
blocker. Implementation sonnets should default to no emojis unless the
stitch pass surfaces a reason to reintroduce them.

---

## 5. Cross-platform tone & style rules

1. **Parallel structure, never platform-default.** When both platforms need
   instructions (Installation, Launch workflows), write them as parallel
   H3 subsections under the same H2 — "### Linux" and "### Windows" — in
   that order (alphabetical, not preference-ranked). Never phrase as "on
   Linux, do X. On Windows, also do Y." That reads as Linux-first
   throwaway-Windows, which is exactly what the current README does.

2. **Forward slashes in prose, native slashes in code blocks.** When
   referencing paths inline (e.g. "see `docs/port-plan/05-install-runbook.md`")
   use forward slashes — they work on both OSes, and both shells accept
   them. Inside Windows-only fenced code blocks (`.bat` contents,
   PowerShell snippets), use backslashes. Inside Git Bash code blocks,
   forward slashes.

3. **Python invocation explicit per platform.** On Linux use
   `python src/gui-v0.8.py` (assuming activated venv). On Windows prefer
   `./venv/Scripts/python.exe src/gui_qt.py` in code blocks (avoids the
   "did you activate?" ambiguity the runbook explicitly works around).
   Don't write `python src/gui_qt.py` for Windows unless activation is
   shown immediately above.

4. **No "just" / no "simply" / no "easy."** The install is not easy.
   Honest documentation acknowledges the setuptools<81 + `--no-build-isolation`
   + torch-from-pytorch.org dance.

---

## 6. Handoff brief for the implementation sonnets

Two parallel sonnet workers, with a stitch pass afterward.

### Sonnet A — "Overview, Install, First Run, Launch" (sections 1–8)

Drafts: Title/badges, Overview, Features, Hardware, Installation-Linux,
Installation-Windows, First run + model download, Launch workflows.

Source docs to consult:
- Existing `README.md` (sections 1–8 worth of salvageable prose)
- `System_dependencies.md` (apt/brew list for Linux install summary)
- `docs/port-plan/05-install-runbook.md` §A, §B, §C, §E (Windows install
  summary + run.bat explanation)
- `docs/port-plan/07-human-verification.md` §D.1, §D.5 (CUDA warmup behavior
  to explain in First Run)
- `run.bat` (quote contents verbatim for the Windows launch section)

Avoid duplicating: Controls, Usage specifics, Model env var, Troubleshooting,
Project structure — all belong to Sonnet B.

Key constraints: parallel OS structure (style rule 1), strict pointer
discipline (do not inline more than ~20 lines from `05-install-runbook.md` —
link to it), and the long-form Linux `.desktop` snippet is a secondary
option only.

### Sonnet B — "Usage, Model, Troubleshooting, Structure, License" (sections 9–13)

Drafts: Usage controls (including the long-recording no-op callout), Model
selection via `$MYTRANSCRIBE_MODEL`, Troubleshooting, Project structure,
License + acknowledgements.

Source docs to consult:
- Existing `README.md` §Controls, §License, §Acknowledgements
- `docs/port-plan/02-ux-contract.md` (MUST items — especially the
  long-recording no-op)
- `docs/port-plan/07-human-verification.md` HT-05 (the long-recording
  no-op contract, the clearest user-facing statement of it)
- `docs/port-plan/05-install-runbook.md` §F (troubleshooting — distill to 5–8
  issues, do not copy all subsections)
- `src/gui_qt.py` lines 67–70, 325–345, 640–660 (for the
  `MYTRANSCRIBE_MODEL` doc)
- `src/gui-v0.8.py` line 74 (for the Linux honest-caveat that the env var
  is Windows-only)

Avoid duplicating: Install steps, Launch workflows, Hardware table — all
belong to Sonnet A.

Key constraints: the long-recording no-op must be its own clearly-styled
callout (blockquote or fenced "Note:" block), not buried in a bullet.
Troubleshooting must be capped at 5–8 items — the full runbook §F is the
authoritative version, the README is the index.

### Stitch pass (a third, short sonnet invocation or the orchestrator)

Responsibilities:
- Resolve overlap between Sonnet A's "First run" section and Sonnet B's
  "Troubleshooting" section (CUDA warmup could plausibly live in either).
  Authoritative placement: First run.
- Apply style rules 1–4 consistently across all sections (especially parallel
  OS structure).
- Verify every pointer to `docs/port-plan/` or `System_dependencies.md`
  resolves to a real anchor or section heading.
- Strip section emojis unless the owner reinstates them during review.
- Verify the Features list items match the actual MUST-items in
  `02-ux-contract.md` — no hallucinated capabilities.
- Final read-through as a fresh contributor on Windows with no prior
  context: can they get to a working transcription in under 30 minutes
  using only this README? If no, flag the gap back to the relevant Sonnet.

---

*End of strategy. Implementation begins when the orchestrator spawns the
two sonnet workers above.*

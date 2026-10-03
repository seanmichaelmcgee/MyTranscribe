# Local session handoff: MyTranscribe Medical on the GTX 1060

This file has three parts:

1. **For you (the human):** about 15 minutes to get a local Claude Code session running.
2. **Kickoff prompt:** paste it into that session.
3. **Brief for the local Claude session:** context, specs, the overnight plan, the
   monitoring protocol and a troubleshooting playbook.

Branch: `claude/festive-einstein-lb2tk9` (PR #4). All test audio is synthetic and
fictional. **No real patient audio or text goes anywhere near this run.**

---

## Part 1: For you (15 minutes, before bed)

### 1. Prerequisites on the GTX 1060 machine
- [ ] **NVIDIA driver** that supports CUDA 12. In a terminal, `nvidia-smi` should show the
      GTX 1060 and "CUDA Version: 12.x". (Any 2024+ Game Ready/Studio driver; the R580
      branch is the last to support GTX 10-series.)
- [ ] **Python 3.11** from python.org, with "Add python.exe to PATH" ticked.
- [ ] **Git for Windows**.
- [ ] **Claude Code**: either the Claude Desktop app (Code tab) or the CLI.
- [ ] About **10 GB free disk** (models ~6 GB, plus environment and results).

### 2. Get the code
```bat
cd %USERPROFILE%
git clone https://github.com/seanmichaelmcgee/MyTranscribe.git
cd MyTranscribe
git checkout claude/festive-einstein-lb2tk9
```
(Already cloned? Run `git fetch origin` then `git checkout claude/festive-einstein-lb2tk9` and `git pull`.)

### 3. Prepare the machine for an overnight run
- [ ] Plugged in. **Pause Windows Update** for a day (Settings → Windows Update → Pause),
      so it doesn't reboot mid-run.
- [ ] Power: the test runner keeps the PC awake while it runs, but to be safe set
      Settings → System → Power → "When plugged in, put my device to sleep after" → **Never**.
- [ ] Stay **logged in**. Locking the screen (Win+L) is fine; signing out or restarting is not.
- [ ] **Close Dragon**, games and anything else using the GPU or the microphone.
- [ ] The Tenor mic isn't needed tonight; the run uses simulated microphones.

### 4. Start the local Claude session
- **Desktop app:** Code tab → open folder `%USERPROFILE%\MyTranscribe`.
- **CLI:** open a terminal in `%USERPROFILE%\MyTranscribe` and run `claude`. Or run
  `claude remote-control` to check on it from your phone via the Claude app.

**Permissions:** an overnight run stalls if Claude stops to ask permission for every
command. Before leaving it, allow commands under `venv1060\Scripts\python.exe`, `git`
and `nvidia-smi` for this project (or use auto mode if you're comfortable with that).
Claude has been told not to touch anything outside this folder.

### 5. Paste the kickoff prompt (Part 2)

Then go to bed. In the morning, read `docs/overnight/<date>-findings.md` (Claude commits
it to the branch) or ask the session for its summary.

---

## Part 2: Kickoff prompt (paste this into the local session)

```
You're running on my Windows PC with the GTX 1060, in my MyTranscribe repo, on branch
claude/festive-einstein-lb2tk9. Read LOCAL_SESSION_HANDOFF.md, Part 3 (the brief for
you), and follow it: set up, get a GO from the preflight, run the quick check, then start
the overnight run for <N> hours and monitor it per the protocol until it finishes.
Write the morning findings file, commit and push it to this branch. Don't push to main,
don't open new PRs, and keep everything inside this folder. I'm going to bed; only stop
to ask me if something needs a decision only I can make (e.g. installing a different
NVIDIA driver). Otherwise log it in the findings and keep going.
```
Replace `<N>` with the hours you'll be away (e.g. 7).

---

## Part 3: Brief for the local Claude session

### 3.1 Mission, in priority order
1. **Get the 1060 edition running on this GPU**: `device=cuda`, `compute=int8_float32`,
   model `large-v3-turbo`. This is the main unknown: nobody has run it on a Pascal GPU yet.
2. **Run the unattended overnight test** (`scripts/overnight_1060.py`) and **monitor it**
   (§3.6). Fix what's fixable, restart what crashed, and record everything.
3. **Morning report** (§3.8), committed to the branch.
4. *Stretch, only if 1–3 are done and healthy:* the on-cursor transcription goals (§3.4).
   Design notes only overnight; don't change app code while the overnight run is going.

### 3.2 What exists and what's already verified
- `src/gui_med.py` is the app (`run_1060.bat`). It reuses the window, hotkey and chimes of
  `src/gui_qt.py`, which must keep working unchanged.
- Engine: `src/fw_engine.py` (faster-whisper/CTranslate2, no PyTorch). Hardware choice:
  `src/hw_profile.py`.
- Chunked background transcription: `src/chunked_transcriber.py`.
- Vocabulary: `src/vocab.py`, `src/vocab/primary_care.txt` (~1,100 FM/IM/peds terms in 19
  topics) and `src/vocab_correct.py` (spelling corrector, 966 extra terms, CC BY 4.0, see
  NOTICE.md).
- Test tools in `scripts/`:
  - `preflight_1060.py`: go/no-go.
  - `run_1060_checks.bat`: one-shot check.
  - `overnight_1060.py`: the overnight loop.
  - `make_test_dictation.py`: synthetic dictations with mic simulation.
  - `eval_dictation.py`: WER and term recall.
  - `bench_engine.py`: speed and VRAM.
  - `stress_pipeline.py`: threading, memory and fault stress.
- **Verified in a Linux cloud VM** (no GPU; random-weight model of the right shape;
  results in `docs/STRESS_TEST_PLAN_1060.md`):
  - 128 unit tests pass.
  - 10 minutes of real-time dictation: RTF 0.30 on CPU, no backlog, no audio lost.
  - A 60-minute session, 300 start/stop cycles, faults and GUI stall < 70 ms all pass.
  - The spelling corrector fixed 76 of 436 real Whisper misrecognitions with 0 wrong
    corrections.
- **Never verified (tonight's job):**
  - CUDA/cuBLAS/cuDNN loading on Windows from the pip wheels.
  - CTranslate2 kernels on compute capability 6.1.
  - Real speed and VRAM use.
  - Real accuracy.
  - SAPI text-to-speech generation.
  - The Windows clipboard privacy formats.
  - The pynput hotkey with the new GUI.

### 3.3 Spec: chunked transcription (don't change these overnight)
| Item | Value | Where |
|---|---|---|
| Capture | 16 kHz, mono, int16; 1024-frame reads (64 ms) | `chunked_transcriber.py` |
| Chunking | Target **30 s**; cut at the quietest 30 ms frame within the last **5 s** (cuts land in pauses); remainder carried over | `CHUNK_TARGET_S`, `CUT_SEARCH_S`, `CUT_FRAME_MS` |
| Threads | Capture thread → queue → one worker thread (transcribes in order). GUI polls every 30 ms, never blocks. Stop returns in < 0.5 s; the tail transcribes in the background ("[Finishing transcription…]") | |
| Memory | Audio kept in RAM only (float32 chunks); **never written to disk**; ~115 MB per hour worst case | |
| Limits | 1 h per recording (`MAX_SESSION_S`); 50 consecutive mic read errors end the session with a message | |
| Silence | Chunks with RMS < 80 (int16) skipped before the model; Silero VAD on (min silence 700 ms, pad 300 ms) | |
| Decoding | `language="en"`, beam 5 (`MYTRANSCRIBE_BEAM_SIZE`), `condition_on_previous_text=False`, no timestamps, faster-whisper default temperature fallback | `fw_engine.py` |
| Prompt | Rebuilt per chunk, ≤ **215 tokens** (Whisper keeps ~223): style example (`prompts/medical_prompt.txt`) + terms for up to 3 active topics + last ~160 chars of transcript. Error markers never enter the prompt | `vocab.py` |
| Post-processing | Phantom-phrase filter (whole-chunk only), then spelling corrector (non-words only, unique close match) | `chunked_transcriber.py`, `vocab_correct.py` |
| Hardware choice | Pascal (CC < 7.0) → `int8_float32`; Turing+ → `int8_float16`; < 3.5 GB VRAM → `small.en`; CUDA load failure → automatic CPU `int8` fallback | `hw_profile.py`, `fw_engine.py` |
| Privacy | Logs record sizes and timings only, never transcript text. Clipboard copies carry Windows "exclude from history / cloud" formats | `phi_clipboard.py` |
| Output | Chunks joined with spaces; final text to clipboard after the worker drains | `gui_med.py` |

### 3.4 Spec: on-cursor transcription (lesser goal)
**What exists:** with `MYTRANSCRIBE_AUTOPASTE=1`:
- After a **Ctrl+Alt+Q stop**, the final text is pasted into whatever window has focus.
- The hotkey does not steal focus at start.
- Paste waits until Ctrl/Alt/Shift are physically released, re-checking every 50 ms for up
  to 3 s.
- Button stops never paste.

**Wanted later (Dragon-like):**
- **Live insert mode:** paste each finished ~30 s chunk at the cursor as it completes,
  instead of everything at the end.
- **Constraints:** the user may move focus mid-dictation, so only paste while focus is
  still in the window that had it at Start (record the foreground window handle at Start;
  on Windows use `GetForegroundWindow`). Otherwise hold the text and paste at Stop.
  Insert a leading space between chunks. Never paste into MyTranscribe itself. Keep the
  clipboard behaviour (privacy formats). Consider restoring the user's previous clipboard
  afterwards.
- **Shorter chunks** for snappier live text (10–15 s) cost accuracy and GPU time; measure
  with `eval_dictation.py` before changing `CHUNK_TARGET_S`.
- **Overnight:** design notes only, in the findings file. Implement in a later session,
  with tests in `tests/test_gui_med.py`.

### 3.5 Run order
**A. Setup**
```bat
scripts\setup_1060.bat
```
This creates `venv1060`, installs `requirements-1060.txt`, downloads the models (~6 GB:
large-v3-turbo, large-v3, distil-large-v3.5) and runs `scripts\preflight_1060.py`. You
need **GO**, with `Auto config: large-v3-turbo cuda int8_float32` and a `GPU smoke test`
PASS on `cuda/...`. On NO-GO, use the playbook (§3.7). The overnight run is still
valuable on CPU if the GPU can't be made to work, but record that prominently.

**B. Quick check (~10 min)**
```bat
scripts\run_1060_checks.bat quick
```
Read `results_1060\SUMMARY.txt`. Fix any obvious breakage before going long.

**C. Overnight run** (in the background, so you stay free to monitor)
```bat
venv1060\Scripts\python.exe scripts\overnight_1060.py --hours <N>
```
It writes to `results_overnight\<YYYYMMDD_HHMM>\`:
- `status.json`: live heartbeat, current task, results.
- `REPORT.md`: rolling table.
- `gpu.csv`: VRAM, utilisation and temperature every 30 s.
- `logs\`: full output of every task.

**Resume** after a crash or reboot with the same `--out <folder>`.

The cycle:
- First cycle only: unit tests, then benchmarks (turbo, turbo beam 1, large-v3,
  distil-large-v3.5).
- Every cycle: `eval` (4 settings × 4 mic profiles), then `long` (30 min of real-time
  conference-mic dictation), then `churn` (200 start/stop cycles, silence, injected
  faults), then `gui` (20 hotkey cycles in the real window).

### 3.6 Monitoring protocol
Check every **30 minutes**. Use `/loop 30m` (or your scheduled wake-ups) with "check the
overnight run per LOCAL_SESSION_HANDOFF.md 3.6"; the run itself is a background process.

Each check:
1. **Heartbeat:** read `status.json`. If `heartbeat` is more than 20 minutes old and
   `phase` is `running`, the runner or a task is hung.
   - Look at `current` and the tail of its log.
   - If a task has clearly hung (no new log lines for 20+ min), kill only that Python
     child process. The runner records it as failed and moves on.
2. **Failures:** for each new `ok: false` task, read its log and classify it:
   - **Environment** (CUDA/DLL/driver, disk, download): fix if safe (§3.7), then let the
     next cycle retry.
   - **Code bug** (traceback in `src/`): don't edit code while the run is going, unless
     the bug makes every remaining task fail. If it does: stop the run, fix, run
     `pytest tests`, commit, restart with `--out` (resume). Otherwise note it for the
     morning.
   - **Threshold miss** (e.g. "UI never froze > 250 ms", or "keeps up" in `long`): record
     the numbers. Don't loosen thresholds.
3. **GPU health** (`gpu.csv`):
   - Memory should stay well under 6144 MB (expect < 4 GB with turbo).
   - Temperature under ~83 °C. If it sits above 85 °C, add `--skip bench` and note it;
     sustained thermal throttling invalidates the speed numbers.
4. **Note each check** in a running log (`docs/overnight/<date>-findings.md`, "Timeline"
   section): one line per check, e.g. `02:30 cycle 2, task long, healthy, VRAM 2.9 GB, 71 °C`.
5. **Don't** start other GPU work, change the vocabulary or thresholds, or commit audio,
   models or the `results_*` folders (they're gitignored; keep it that way).

### 3.7 Troubleshooting playbook
| Symptom | Likely cause | Action |
|---|---|---|
| `cuda devices 0`, or `CUDA probe failed` | Driver too old, or DLLs not found | Check that `nvidia-smi` works. Reinstall `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` in venv1060. Confirm `fw_engine.register_cuda_dll_dirs()` returns 2+ folders. Driver install needs the user: ask, or note it and continue on CPU |
| `cublas64_12.dll` / `cudnn_ops64_9.dll` not found | DLL search path | Same as above; check `venv1060\Lib\site-packages\nvidia\*\bin` exists |
| `no kernel image is available for execution on the device` | This CTranslate2 build lacks Pascal (sm_61) kernels | Try older wheels in venv1060, one at a time, re-running preflight after each: `ctranslate2==4.6.0`, then `4.5.0`. Last resort: `4.4.0` with `nvidia-cudnn-cu12==8.9.7.29` (4.4 uses cuDNN 8). Record which works and pin it in `requirements-1060.txt` (commit) |
| Preflight picks `int8_float16` on the 1060 | nvidia-smi missing, so the card is unidentified | Set `MYTRANSCRIBE_COMPUTE_TYPE=int8_float32` and report it. Check `hw_profile.find_nvidia_smi()` |
| CUDA out of memory | Desktop/other apps using VRAM, or large-v3 with beam 5 | Close GPU apps. For the large-v3 bench only, note it. Turbo should never OOM on 6 GB: if it does, that's a finding |
| "Transcription is falling behind" in `long` | GPU too slow at beam 5 | Record the RTF. Compare `bench_turbo_beam1`. Don't change defaults overnight |
| `make_testdict` fails (SAPI) | No Windows voices / PowerShell policy | `python scripts\make_test_dictation.py --list-voices`. Install a voice (Settings → Time & language → Speech), or install espeak-ng and use `--backend espeak` |
| `gui` task fails or hangs | Session locked/disconnected, or the pynput hook blocked | Note it; skip with `--skip gui` on resume. Not a blocker for the other tasks |
| Unit tests fail only on Windows | Path/encoding/Qt platform differences | Note the failing tests. Fix in the morning session, not overnight |
| Model download fails | No internet / Hugging Face blocked / proxy | Can't fix overnight: note it; preflight will be NO-GO |
| Antivirus quarantines DLLs or blocks keyboard hooks | Defender heuristics | Note it; don't disable security software. Ask the user in the morning |

### 3.8 Morning deliverable
Create `docs/overnight/<YYYY-MM-DD>-findings.md`, then commit and push it to this branch
(not the results folders; small JSON summaries may be pasted inline). Template:

```markdown
# Overnight findings <date>
## TL;DR (5 lines max)
## Environment
GPU / driver / CUDA / ctranslate2 version / compute types / auto config / any version pins changed
## Speed & memory (bench)
| model | beam | RTF | peak VRAM | WER |
## Accuracy (eval, last full cycle)
| setting | clean | headset | conference | noisy | (WER % / term recall %)
Most-missed terms (fictional data, safe to list):
## Stability (long / churn / gui across all cycles)
pass/fail counts, worst final latency, max queue, RSS trend, worst UI stall
## GPU health
peak VRAM, peak temperature, throttling?
## Failures and what was done
## Recommendations
defaults to change? (model / beam / chunk length / vocab) with the numbers behind them
## On-cursor design notes (§3.4)
## Timeline
```
Also paste the TL;DR into the chat for the user.

### 3.9 Ground rules
- **No PHI, ever.** Synthetic audio only. Don't record the microphone, and don't read any
  files outside this repo.
- Work only on branch `claude/festive-einstein-lb2tk9`. Never push to `main`; no new PRs.
- Don't commit audio, models, `results_1060/` or `results_overnight/` (all gitignored).
- Before any code commit: `venv1060\Scripts\python.exe -m pytest -q tests` must pass. Keep
  `src/gui_qt.py` behaviour unchanged.
- Don't weaken the spelling corrector's safety rules (non-words only, unique match).
  `tests/data/whisper_misrecognitions.tsv` must keep passing.
- When unsure whether something is a decision for the user, log it and move on. Only stop
  to ask for things you can't do yourself (drivers, security software, buying hardware).

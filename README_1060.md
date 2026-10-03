# MyTranscribe Medical: GTX 1060 edition

A separate version of MyTranscribe for **long dictation (letters, notes) on older NVIDIA
cards**, built around a GTX 1060 6 GB. The original app (`src/gui_qt.py`, `run.bat`) is
unchanged and still works; this one lives alongside it.

| | Original (`gui_qt.py`) | Medical / 1060 (`gui_med.py`) |
|---|---|---|
| Engine | openai-whisper + PyTorch | faster-whisper (CTranslate2), **no PyTorch** |
| Default model on a 1060 | `large-v3` (does not fit in 6 GB) | `large-v3-turbo`, int8 weights (~1.6 GB VRAM) |
| When is audio transcribed? | All at once when you press Stop (window freezes) | In ~20 s pieces **while you talk**; Stop only waits for the last piece |
| Audio written to disk? | Yes, temp WAV files (may be left behind on Windows) | **Never**: kept in memory only |
| Transcript in the console log? | First 60 characters | **Never**: length only |
| Windows clipboard history / cloud sync | Keeps a copy | Each copy is marked "don't keep, don't sync" |
| Vocabulary | Programming terms | ~1,100 primary-care terms (FM, IM, peds) picked per chunk by topic, plus spelling correction of near-miss drug names |
| Long recordings | 3 min cap in Long mode | 1 hour per recording; one Start/Stop button (no separate Long mode) |
| Start/stop | Buttons, Space, Ctrl+Alt+Q | Also **F9 (hold to talk)** and the **mouse forward button (toggle)**, changeable in Options |
| Clipboard | Copy, unchecked | **Verified** copy; if another program holds the clipboard it says "Not copied" and never pastes old text |
| Auto-paste into your app | No | Optional (`MYTRANSCRIBE_AUTOPASTE=1`) |

## Install (Windows)

Needs Python 3.11 and a CUDA-12-capable NVIDIA driver (any recent Game Ready or Studio
driver; the R580 branch is the last to support GTX 10-series cards).

**Easiest:** `scripts\setup_1060.bat` creates the environment, installs everything,
downloads the models and runs a go/no-go check (`scripts\preflight_1060.py`).
Overnight unattended testing with a local Claude session: see
[LOCAL_SESSION_HANDOFF.md](LOCAL_SESSION_HANDOFF.md).

Manual install:

```bat
cd C:\path\to\MyTranscribe
py -3.11 -m venv venv1060
venv1060\Scripts\python.exe -m pip install -r requirements-1060.txt
run_1060.bat
```

On the **first run** the model (~1.6 GB for turbo, ~3 GB for large-v3) is downloaded from Hugging Face into
`%USERPROFILE%\.cache\huggingface`. The window says "Loading speech model…" and the
buttons unlock when it's ready. After that, everything runs offline; set
`HF_HUB_OFFLINE=1` (see `run_1060.bat`) to guarantee nothing is contacted.

The console prints the chosen setup, e.g.
`Engine config: model=large-v3 device=cuda compute=int8_float32 ... GPU NVIDIA GeForce GTX 1660 Ti (CC 7.5, 6144 MB): fast fp16, best-accuracy model`.
On GTX 10xx and 16xx cards you want `device=cuda` and `compute=int8_float32` (measured
26-29 % faster than `int8_float16` on a GTX 1660 Ti). If it says `device=cpu`, see
Troubleshooting.

**Antivirus HTTPS scanning (Norton, Avast, corporate proxies):** if `pip install` fails
with `CERTIFICATE_VERIFY_FAILED`, your security software is re-signing HTTPS traffic.
Don't turn verification off. Export its root certificate from the Windows certificate
store, append it to a copy of pip's `cacert.pem`, and point `venv1060\pip.ini`
(`[global] cert = ...`) and `REQUESTS_CA_BUNDLE` at that file for the install and the
first model download.

## Use

The window starts small (compact view) and stays on top of other windows:

- The **round light** at the top left is **green while recording, red when not**.
- **F9**: hold to talk; release to stop. **Mouse forward (thumb) button**: press to start,
  press again to stop. These presses are swallowed, so your EMR never sees them.
- **Ctrl+Alt+Q** from any app, or **Space** with the window focused: start/stop.
  The big **Start dictation / Stop** button does the same.
- Hotkeys never pull MyTranscribe to the front, so your cursor stays in the EMR.
- When you stop, the text is copied (status: "Copied — paste with Ctrl+V"). If the status
  says **Not copied**, another program was using the clipboard: click **Copy**, then paste.
- **Voice commands:** say "new line", "new paragraph", or "open quote … close quote".
  They only count when you pause around them (Whisper then punctuates them), so
  "a new line of therapy" stays as text. Turn off in Options.
- **Numbered items:** "new line, 1 period, dry eyes…" → a new line starting "1. Dry eyes…".
- **Type as you dictate** (Options, off by default): each finished ~20 s piece is pasted
  at your cursor while you keep talking, only into the window you started in (never into
  MyTranscribe, held if you click elsewhere), and the full text is on the clipboard when
  you stop.
- **Microphone kept ready** (Options, on by default): like Dragon, the mic stays open
  and the last half-second is kept in memory, so a word spoken as you press Start isn't
  clipped (Bluetooth headsets otherwise drop ~0.3 s). Windows shows the mic as in use
  while the app is open. Turn it off and the light shows amber until the mic is live.
- **+** shows the transcript (live while you talk), **–** hides it again.
- **⚙ Options**: change the key, the mouse button, hold-to-talk vs toggle, accuracy
  (Best = large-v3, Fast = large-v3-turbo; applies next start) and the start-up view.
  Saved in `%APPDATA%\MyTranscribe\settings.json` (bindings and view only, never text).
- One recording can run up to an hour. Text is transcribed in ~20 s pieces while you
  talk; after Stop only the last piece is left. On a GTX 1660 Ti with the default
  large-v3: short notes ~1 s after Stop, 20-60 s dictations ~1.3-2.5 s
  ([day findings](docs/overnight/2026-10-03-day-findings.md)).

**Auto-paste mode** (`set MYTRANSCRIBE_AUTOPASTE=1` in `run_1060.bat`): click into your
EMR/Word field, press Ctrl+Alt+Q, dictate, press Ctrl+Alt+Q again. When transcription
finishes, the text is pasted where your cursor is. In this mode the hotkey does not
bring the MyTranscribe window to the front, so your cursor stays put. Stopping with the
on-screen button never auto-pastes (focus would be on MyTranscribe itself). Some
remote/Citrix EMRs block simulated keystrokes; if so, paste with Ctrl+V yourself.

**Always proofread** drug names, doses, laterality and numbers before signing.

## Medical vocabulary

Whisper can only take a short hint (~220 tokens, about 150 words) before each piece of
audio. The app builds that hint fresh for every ~20 s chunk:

1. **Your style**: `src/prompts/medical_prompt.txt`, a short letter opening in your voice.
2. **Topic terms** from `src/vocab/primary_care.txt`: about 1,100 terms in 19 topics
   (hypertension, diabetes, respiratory, pediatric acute, well-child, immunization, and so
   on). The topics you've just been dictating about are switched on by their trigger
   words, and their drugs, tests and diagnoses go into the hint. Long letters rotate
   through each topic's list.
3. **Your last few sentences**, so names and terms carry over between chunks.

After each chunk, a **spelling corrector** fixes near-miss non-words to the right term
("licenopril" → lisinopril, "semiglutide" → semaglutide). It only touches words that are
neither real English nor known terms, and leaves anything ambiguous alone, so a correctly
heard drug is never swapped for a sound-alike. It uses the topic list plus a 966-term
general medical list (see NOTICE.md).

**Make it yours:**
- Edit `src/prompts/medical_prompt.txt` in your own letter style (no real patient details).
- Add your colleagues, local services and favourite drugs to a file of your own, e.g.
  `C:\MyTranscribe\my_terms.txt`, and set `MYTRANSCRIBE_VOCAB_FILES` to point at it:
  ```
  ## core | letter
  other: Dr. Okonkwo-Bailey, Dr. Nguyen, Riverside Pediatrics, CHEO
  ## diabetes | diabetes
  drug: Ozempic, Rybelsus
  ```
  Terms under `## core` are always eligible; other sections join the matching topic.

## Settings (environment variables)

Most people only need the Options screen. Environment variables override it (handy for
testing):

| Variable | Default | Meaning |
|---|---|---|
| `MYTRANSCRIBE_KEY` / `MYTRANSCRIBE_KEY_MODE` | `f9` / `hold` | `f1`-`f12`, `pause`, `scroll_lock` or `none` / `hold` or `toggle` |
| `MYTRANSCRIBE_MOUSE` / `MYTRANSCRIBE_MOUSE_MODE` | `x2` / `toggle` | `x2` (forward), `x1` (back), `middle` or `none` / `hold` or `toggle` |
| `MYTRANSCRIBE_MODEL` | `large-v3` (GPU ≥ 5 GB, Options → Best), else `large-v3-turbo`; `small.en` (CPU) | Any faster-whisper name (`large-v3-turbo`, `medium.en`…) or a local model folder |
| `MYTRANSCRIBE_COMPUTE_TYPE` | auto (`int8_float32` on GTX 10xx/16xx, `int8_float16` on RTX) | CTranslate2 compute type |
| `MYTRANSCRIBE_DEVICE` | auto | `cpu` forces CPU |
| `MYTRANSCRIBE_BEAM_SIZE` | `1` (greedy) | `5` = beam search: ~30 % slower, no accuracy gain in our tests, and it sometimes drops spoken commands |
| `MYTRANSCRIBE_AUTOPASTE` | off | `1` = paste into the focused app after a hotkey stop |
| `MYTRANSCRIBE_PROMPT_FILE` | bundled medical prompt | Your style example |
| `MYTRANSCRIBE_VOCAB` | on | `off` = style example only, no topic terms |
| `MYTRANSCRIBE_VOCAB_FILES` | none | Extra vocabulary files (`;`-separated on Windows) |
| `MYTRANSCRIBE_VOCAB_TOPICS` | none | Topics to assume before you've said anything, e.g. `peds-acute,respiratory` |
| `MYTRANSCRIBE_AUTOCORRECT` | on | `off` = no spelling correction |
| `HF_HUB_OFFLINE` | off | `1` = never contact Hugging Face (after first download) |

## Check speed and accuracy on your machine (no microphone needed)

```bat
scripts\run_1060_checks.bat          :: about 45-60 min, unattended
scripts\run_1060_checks.bat quick    :: about 10 min
```

This generates fictional dictations with Windows' built-in voices, simulates four
microphones (clean, headset, **conference mic** such as a Tenor, noisy room), and
runs them through the real model on your GPU. It reports speed, VRAM, word error
rate and **medical-term recall** with and without the vocabulary features, then
stress-tests the pipeline. Send back `results_1060\SUMMARY.txt`.

Computer voices mispronounce some drug names, so treat the absolute numbers as a
pessimistic floor and use them to *compare* settings. For real numbers, read the
scripts in `results_1060\testdict\read_aloud\` into your own mic and score them with
`scripts\eval_dictation.py` (see its `--help`).

**Short notes with your own voice (~10 min):** 27 fictional snippets in three styles
(messages with "new line"/quotes, results comments, exam findings):

```bat
venv1060\Scripts\python.exe scripts\make_snippets.py
venv1060\Scripts\python.exe scripts\record_snippets.py --out results_1060\real_headset
venv1060\Scripts\python.exe scripts\eval_snippets.py --manifest results_1060\real_headset\manifest.json --settings large-v3:b1,large-v3-turbo:b1 --show-text
```

The first command makes the synthetic versions for comparison. The second shows each
snippet; Enter starts/stops recording. The third reports word error rate, key terms,
whether line breaks/quotes came out right, and the wait after Stop, per model.
`scripts\latency_bench.py` measures Stop-to-text time by dictation length.

## Privacy checklist (your side)

The app keeps audio in memory and never logs transcript text, but the machine still
needs: BitLocker (full-disk encryption), a login password and auto-lock, and Windows
**Settings → System → Clipboard → Clipboard history: Off** and **Sync across devices:
Off** (belt and braces; the app already opts each copy out). This is not legal advice;
check with whoever handles privacy compliance for your practice.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Console says `device=cpu` / `CUDA probe failed` | Update the NVIDIA driver; confirm `nvidia-smi` works in a terminal; reinstall `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` into `venv1060` |
| `Could not load library cudnn_ops64_9.dll` (or `cublas64_12.dll`) | Same as above; the app falls back to CPU automatically meanwhile |
| "Could not load the speech model" on first run | No internet for the one-time download, or `HF_HUB_OFFLINE=1` set too early |
| "Transcription is falling behind" warnings | Set `MYTRANSCRIBE_BEAM_SIZE=1`, or `MYTRANSCRIBE_MODEL=distil-large-v3.5` / `small.en` |
| Auto-paste does nothing in the EMR | Remote/Citrix session blocking simulated keys: use Ctrl+V |
| Words wrong at a ~20 s boundary | Report it: cuts are made at the quietest moment, but a long run-on sentence can still be split |

## Running the tests (developers)

```bash
pip install -r requirements-1060.txt
xvfb-run -a python -m pytest tests     # Linux headless; on Windows just: python -m pytest tests
```

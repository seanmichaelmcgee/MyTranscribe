# MyTranscribe Medical: GTX 1060 edition

A separate version of MyTranscribe for **long dictation (letters, notes) on older NVIDIA
cards**, built around a GTX 1060 6 GB. The original app (`src/gui_qt.py`, `run.bat`) is
unchanged and still works; this one lives alongside it.

| | Original (`gui_qt.py`) | Medical / 1060 (`gui_med.py`) |
|---|---|---|
| Engine | openai-whisper + PyTorch | faster-whisper (CTranslate2), **no PyTorch** |
| Default model on a 1060 | `large-v3` (does not fit in 6 GB) | `large-v3-turbo`, int8 weights (~1.6 GB VRAM) |
| When is audio transcribed? | All at once when you press Stop (window freezes) | In ~30 s pieces **while you talk**; Stop immediately sends any shorter remainder |
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

`scripts\setup_1060.bat` downloads the model (~1.6 GB for turbo, ~3 GB for large-v3) from Hugging Face into
`%USERPROFILE%\.cache\huggingface`. If it is missing when the app starts, the app **asks before
downloading** and says where the model comes from, its size and its licence. The window says
"Loading speech model…" and the buttons unlock when it's ready. Otherwise the app never contacts
the internet: it runs with the Hugging Face hub offline whichever way it is started.

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

## Window and sound options

The Options gear includes a start/stop sound volume slider (0% mutes both sounds)
and “Paste automatically after stopping dictation”. Save applies these immediately
and remembers them for the next launch. Auto-paste requires stopping with a hotkey;
the on-screen Stop button copies only. An explicit MYTRANSCRIBE_AUTOPASTE environment
variable overrides the saved choice; remove it to control auto-paste in Options.

Compact view now targets 300 logical pixels wide with tighter spacing. The light,
input meter, Copy, Options, expand control and Start/Stop remain available. Options
uses explicit light colours for readability even when Windows uses dark mode.

## Pause-aware dictation (optional, off by default)

Options → Text → “Pause-aware dictation”. Try it if pausing to think puts full stops
in the middle of your sentences, if “new paragraph” / “new line” are sometimes ignored,
or if the last word goes missing when you release the key. With it on:

- a sentence you paused in is kept together across the app's internal ~30 second pieces;
- a spoken “new paragraph” or “new line” that the speech model skipped is put back, and
  one it wrote without punctuation still counts;
- the microphone keeps listening for 0.3 seconds after Stop, so the last word is not cut.

Untick it to return to the original behaviour at once (from the next recording). It
was measured on fictional practice recordings with artificial pauses, not yet in daily
use: results and known limits are in
[docs/optimization/2026-11-15-dictation-reliability.md](docs/optimization/2026-11-15-dictation-reliability.md).
`MYTRANSCRIBE_PAUSE_AWARE=1` (or `0`) overrides the saved choice.

**Spoken punctuation** (Options, off by default) is for dictating the marks yourself:
"period" / "full stop", "comma", "colon", "semicolon", "question mark", "exclamation mark",
"hyphen" and "open / close parenthesis" become the marks. "Her last period", "a period of
observation", "the sigmoid colon" and "colon cancer" stay words, but that check is a word
list and can be wrong on an unusual phrase, so read the result. Leave it off if you let the
app punctuate for you. `MYTRANSCRIBE_SPOKEN_PUNCTUATION=1` (or `0`) overrides the saved choice.

**Only the commas I dictate** (Options, off by default; needs Spoken punctuation) removes the
commas the model adds by itself and keeps the ones you say, the way Dragon behaves. For people
who dictate every comma. `MYTRANSCRIBE_ONLY_DICTATED_COMMAS=1` (or `0`) overrides the saved choice.

**Extra corrections** (Options, off by default) fixes a misspelled drug or term when it
sounds exactly like one vocabulary word and no other ("prendipril" becomes perindopril), and
writes readings the chart way: "138 over 78" as 138/78, "g per litre" as g/L, "degrees
Celsius" as °C. It also puts a misheard drug name right where the sentence says a drug
belongs ("renew Ram and Pearl 5 mg" becomes ramipril, "caprigolin 0.5 mg weekly" becomes
cabergoline), using a list of 2,400 approved drug names. On synthetic dictation it fixed 162
names and made 4 wrong changes, so check drug names as you always would. And it writes out
a contraction the model put where the full words were said, when the next word makes the
meaning certain ("I'd be grateful" as "I would be grateful", "There's no" as "There is no");
"didn't" and the like stay as said.
`MYTRANSCRIBE_EXTRA_FIXES=1` (or `0`) overrides the saved choice.

## Starting without a console window

`run_1060.bat` keeps a console open with the log, which is handy when something is wrong.
For everyday use:

- `MyTranscribe-personal.bat` is the same start with the owner's dictation options on for
  that start, whatever is saved in Options: pause-aware dictation, spoken punctuation, Extra
  corrections and only-dictated commas, in English with Whisper.
- `MyTranscribe.bat` starts the app and closes its own window at once, or
- run `scripts\make_shortcut.ps1` once (PowerShell) for a desktop shortcut that shows no
  console at all.

Either way the app writes its messages to `%LOCALAPPDATA%\MyTranscribe\mytranscribe.log`
(1 MB, two older copies kept) and **Options → Show log** opens the recent ones in their own
window, with Copy and Open folder buttons. The log holds timings, lengths and errors, never
what you dictated. The app works offline by default however it is started; it no longer needs
`HF_HUB_OFFLINE=1` from the batch file.

## Choosing the recogniser (Options → Speech model)

**Recogniser** switches the model that listens. Saving a change reloads it in a few seconds
(after the current dictation, if one is running); no restart. Whisper is the default and the
only one the standard install provides. The others are listed with the reason they are
unavailable until their packages and model are present (`requirements-engines.txt`).
Options offers Whisper and MedASR. **MedASR's licence terms must be accepted before use**: Google
releases it only to people who have accepted its Health AI Developer Foundations terms with their
own Hugging Face account, so every person who uses it must do that themselves. Parakeet and Canary
were clearly behind on medical dictation and are kept for trials only (`MYTRANSCRIBE_ENGINE=parakeet`).

| Recogniser | Model source | Size | Licence and access | Notes |
|---|---|---|---|---|
| Whisper large-v3 (default; "Fast" = large-v3-turbo) | Hugging Face `Systran/faster-whisper-large-v3` | 3 GB (turbo 1.6 GB) | MIT; no account | Most accurate here; the only one that uses your vocabulary |
| MedASR | Hugging Face `google/medasr` (gated) | 0.4 GB + PyTorch 2.5 GB | Health AI Developer Foundations terms: accept them with **your own** Hugging Face account, sign in, then `scripts\download_medasr.py` | About ten times faster; good drug names; loses people's names and sometimes the first words |
| Parakeet 0.6B v2 | Hugging Face `istupakov/parakeet-tdt-0.6b-v2-onnx` (community ONNX export of NVIDIA's model) | 2.4 GB | CC BY 4.0; no account | Fastest; general English, no medical vocabulary |
| Canary 1B v2 | Hugging Face `istupakov/canary-1b-v2-onnx` (community ONNX export) | 3.7 GB | CC BY 4.0; no account | General English, no medical vocabulary |

**When is a model downloaded?** Never silently. `scripts\setup_1060.bat` fetches the Whisper
models at install time. If you pick a recogniser whose model is not on the PC, the app asks
first and shows where it comes from, how big it is and its licence; on Yes it downloads that
model only and goes back to offline. Nothing you dictate is ever sent. MedASR cannot be
fetched by the app: Google requires each user to accept its terms personally, so that one is
a manual step (see `docs/MEDASR_TRIAL.md`). Read each licence yourself before relying on a
model at work; the table is a summary, not legal advice.

How they compare on the same recordings is in
[docs/optimization/2026-11-15-dictation-reliability.md](docs/optimization/2026-11-15-dictation-reliability.md).
Pause-aware dictation needs word timings: it works with Whisper and Parakeet and is skipped
for MedASR and Canary. MedASR always converts dictated punctuation, because it writes the
marks as words by itself.

## Other languages (experimental)

**Options → Speech model → Dictation language** switches between English, Spanish, French and
Swahili (or `MYTRANSCRIBE_LANGUAGE=es`). It is the same Whisper model: no extra download for
Spanish or French. All the options work in each language: spoken formatting and punctuation
in that language's own words ("punto y aparte", "coma", "à la ligne", "virgule", "aya mpya",
"nukta"), pause-aware dictation, and extra corrections (readings, units, and for Spanish and
French a draft medical term list). The English vocabulary and corrector are switched off.

- **Spanish and French:** 2.3% and 5.5% word errors on public test sentences. On real French
  medical dictation (7 notes) the French pack took word errors from 33% to 8.7%.
- **Swahili:** standard Whisper gets more than one word in three wrong (38.7%). A model tuned
  for Swahili halves that (20.5%); install it once with
  `python scripts\convert_whisper_model.py --repo cdli/whisper-large-v3-swahili-afrivoice-cv --language sw`
  (6 GB download, Apache 2.0, needs the optional packages in `requirements-engines.txt`). The
  app then uses it whenever Swahili is chosen. Still a demonstration, not a clinical tool.
- The command words, term lists and reading sets are drafts that no clinician has dictated
  with yet; the Swahili ones have not been checked by a Swahili speaker.

Details and limits: [docs/optimization/2026-11-16-multilingual.md](docs/optimization/2026-11-16-multilingual.md).

## Use

The window starts small (compact view) and stays on top of other windows:

- The **round light** at the top left is **green while recording, red when not**.
- The **small microphone level bar** stays visible in compact view. It shows the
  captured input, before speech filtering: amber means low input, red means nearly
  clipped input. The recording light stays green even during a silent pause.
  No automatic gain is applied; Windows or microphone hardware may apply their own
  processing before audio reaches the app. Very quiet or whispered speech needs
  testing with your own microphone.
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
- **Type as you dictate** (Options, off by default): each finished ~30 s piece is pasted
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
- One recording can run up to an hour. Longer speech uses ~30 s pieces for context;
  a short recording is sent immediately when you stop, without waiting for 30 s.
  On this GTX 1660 Ti, large-v3 finishing delay in the paced saved-voice trial was
  typically ~1.0–1.5 s for short workflows and ~2.6 s for the three letters.
  These exclude GUI/clipboard time and are observations, not latency guarantees
  ([matched accuracy and timing report](docs/overnight/2026-10-04-asr-optimization.md)).

**Auto-paste mode** (`set MYTRANSCRIBE_AUTOPASTE=1` in `run_1060.bat`): click into your
EMR/Word field, press Ctrl+Alt+Q, dictate, press Ctrl+Alt+Q again. When transcription
finishes, the text is pasted where your cursor is. In this mode the hotkey does not
bring the MyTranscribe window to the front, so your cursor stays put. Stopping with the
on-screen button never auto-pastes (focus would be on MyTranscribe itself). Some
remote/Citrix EMRs block simulated keystrokes; if so, paste with Ctrl+V yourself.

**Always proofread** drug names, doses, laterality and numbers before signing.

## Medical vocabulary

Whisper can only take a short hint (~220 tokens, about 150 words) before each piece of
audio. The app builds that hint fresh for every ~30 s chunk:

1. **Your style**: `src/prompts/medical_prompt.txt`, a short letter opening in your voice.
2. **Topic terms** from `src/vocab/primary_care.txt`: about 1,100 terms in 19 topics
   (hypertension, diabetes, respiratory, pediatric acute, well-child, immunization, and so
   on). The topics you've just been dictating about are switched on by their trigger
   words, and their drugs, tests and diagnoses go into the hint. Long letters rotate
   through each topic's list.
3. **Your last few sentences**, so names and terms carry over between chunks.

The complete hint is measured against a 215-token budget. Recent context takes
priority; an oversized style example keeps its whole-word ending. Keep examples
brief and put the most important terms near the end.

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
  Terms under `## core` accompany a detected or configured topic; other sections
  join the matching topic. With no known topic, the hint contains no term list.

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
| `MYTRANSCRIBE_BEAM_SIZE` | `5` | Beam search with patience 2; current real-voice calibration favors this for medical accuracy and formatting. `1` trades accuracy for speed. See [runtime results](docs/overnight/2026-10-04-whisper-runtime.md). |
| `MYTRANSCRIBE_AUTOPASTE` | off | `1` = paste into the focused app after a hotkey stop |
| `MYTRANSCRIBE_PROMPT_FILE` | bundled medical prompt | Your style example |
| `MYTRANSCRIBE_VOCAB` | on | `off` = style example only, no topic terms |
| `MYTRANSCRIBE_VOCAB_FILES` | none | Extra vocabulary files (`;`-separated on Windows) |
| `MYTRANSCRIBE_VOCAB_TOPICS` | none | Topics to assume before you've said anything, e.g. `peds-acute,respiratory` |
| `MYTRANSCRIBE_AUTOCORRECT` | on | `off` = no spelling correction |
| `HF_HUB_OFFLINE` | `1` (set by the app) | The app works offline and asks before any model download. `0` lets the model libraries contact Hugging Face on every start |

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
| "Could not load the speech model" on first run | The model is not on this PC and the download was declined or failed (no internet). Start again and answer Yes, or run `scripts\setup_1060.bat`. Options → Show log has the details |
| "Transcription is falling behind" warnings | Set `MYTRANSCRIBE_BEAM_SIZE=1`, or `MYTRANSCRIBE_MODEL=distil-large-v3.5` / `small.en` |
| Auto-paste does nothing in the EMR | Remote/Citrix session blocking simulated keys: use Ctrl+V |
| Words wrong at a ~30 s boundary | Report it: cuts are made at the quietest moment, but a long run-on sentence can still be split |

## Running the tests (developers)

```bash
pip install -r requirements-1060.txt
xvfb-run -a python -m pytest tests     # Linux headless; on Windows just: python -m pytest tests
```

# Setup wizard and tuning to your voice: plan

Status (2026-11-18): **phase 1 is built**. The questions, the microphone choice and check, first-start
detection and "Run setup again" in Options are in `src/setup_wizard.py`, `src/mic_check.py` and
`src/audio_devices.py`, tested in `tests/test_setup_wizard.py`. They have not yet been tried by a
person on a fresh install. Phases 2–5 are still plans.

**Phase 1 as built.**
- **Pages.** The wizard asks about this computer, the microphone, how you dictate, where the
  text goes, and start/stop, then shows a summary that lists what changed.
- **"What you mostly dictate."** Left for phase 2, because nothing in phase 1 would use the
  answer.
- **Usual medications page.** Also phase 2.
- **Microphone check.** It measures raw audio, before the gain:
  - it leaves the gain at 50 when the voice is already at a good level;
  - otherwise it raises or lowers the gain, but never so far that the room's noise reaches the
    app's speech-level check;
  - its warnings cover clipping, a voice that is still too quiet, a noisy room, a voice close
    to the background, and Bluetooth headsets.
- **Microphones are chosen by name.** Windows' MME system cuts names to 31 characters; the full
  name is taken from DirectSound. A saved microphone that is unplugged falls back to the
  Windows default.
- **Backup.** Running setup again keeps the replaced settings in `settings.before-setup.json`.

## The idea

The first time MyTranscribe Medical starts, a short wizard asks how the person will use it
and sets the options to match. It covers:

- whether they say the punctuation;
- whether they want text typed as they talk, or a little more accuracy with the text all at once;
- how they start and stop;
- which microphone to use.

Then, if they want, it shows a few fictional texts written for how they dictate. They read
those texts aloud, and the app adjusts itself to their voice, microphone and room. It shows
their word error rate before and after. The wizard can be run again at any time from Options.

## What the evidence says is worth tuning for each person

The project has a long record of what changed word errors and what did not. It points away
from "try many recognition settings and keep the best". The gains for a new person are
mostly in four places: the right dictation mode, their usual medications, their microphone,
and a handful of word fixes.

**Worth setting or tuning for each person**

| What | Measured effect | How the wizard sets it |
|---|---|---|
| Spoken punctuation, and "only the commas I dictate" | The biggest single factor. On Corti, Whisper as it comes scores 44.9%, almost all of it "period", "comma" left in as words; with the marks converted, 14.2%. The wrong choice costs more than anything else. | Asked, then checked against the reading: did they actually say the marks? |
| Usual medications list | The owner's dictated letters: 2.44% → 1.22% word errors, every drug name right. | Asked: type or paste the drugs they prescribe most. |
| Personal word fixes (`heard => meant`) | Fixes one word everywhere it appears, for example "eMERG" → "emerg". | Proposed from the reading; the person approves each one. |
| Microphone choice and level | The level bar shows amber when the microphone is too quiet. Quiet and whispered speech is untested. The silence check uses a fixed level (80). The app always uses the Windows default microphone. | Measured: room noise, then speech. The wizard picks the device and sets gain. |
| Typing as you talk vs text at Stop | 2.91% vs 2.35% word errors (54 recordings). Text appears every ~6 s, or all at Stop. | Asked, with these numbers shown. |
| Model (best or fast) | Set by the graphics card. | Detected, with the expected wait shown. |

**Not worth tuning for each person** (no gain beyond noise, or a risk)

| What | Evidence |
|---|---|
| Beam size, number precision | Beam 8 vs 5: 10.59% vs 10.48%. float16: 10.38%. Within noise. |
| Silence detection padding (VAD) | Three variants tried, none better. |
| Window length 15 / 20 / 30 s | Within noise on 40 files; 15 s only for typing as you talk. |
| Rewriting the style example (prompt) | Risky. A "letter mode" example made no difference and added a nonsense phrase. A minimal style raised medical errors to 7.1%. A style example can copy its values into a short dictation. |

So a run that tries "a few times to get better word error rates" has a small space to
search, and the plan keeps it small on purpose. Each change it can make is one a person can
understand and undo.

## What it builds on

- **Options:** `src/settings.py` and `src/options_dialog.py` already hold every option the
  wizard sets.
- **Replay and scoring:**
  - `scripts/dictation_reliability.py` (`FileMic`, `run_pipeline`) replays saved audio
    through the real app pipeline under any set of options;
  - `src/eval_metrics.py` (`align`) and `word_edits`, `format_ok`, `command_hits` score the
    result.
- **Reading sets:** `scripts/validation_tool.py` provides:
  - fictional reading sets (`validation/validation_set_v1.txt`, `v2`);
  - `spoken_form()`, which writes any reference as it would be dictated ("period",
    "new paragraph");
  - a recorder;
  - splitting one long recording at "break break".
- **The user's own files** in `%APPDATA%\MyTranscribe\`: `corrections.txt` and
  `my_medications.txt`. The app already reads both.
- **Microphone handling:** the level meter, the gain slider, and `speech_level()`, which
  already measures a chunk's noise floor.
- **The owner's `personal` profile:** what an expert user chose. Answering the wizard the
  owner's way should produce exactly those settings, which makes a good first test.

## The wizard, page by page

Each page asks one thing, in plain words, with the recommended choice already selected. Every
page has **Back** and **Skip**. The first page also offers **Use recommended settings**, which
skips everything.

0. **Welcome.** What the wizard does: about 3 minutes for the questions, about 10 more for
   the optional reading.
1. **This computer.** The graphics card is detected and the model chosen (best or fast). The
   model is downloaded only with permission (what, from where, size, licence: the existing
   prompt). A short timing test gives "expect text about N s after you stop".
2. **Microphone.**
   - Pick the microphone (new setting; today the Windows default is always used).
   - 5 seconds of quiet measures room noise; one read sentence measures speech level.
   - Gain is set so speech sits in the green band, with warnings for clipping, a noisy room,
     or a Bluetooth headset (it opens slowly).
   - This page can also be run on its own later, for example after changing headsets.
3. **How you dictate.**
   - **Punctuation:**
     - "I say every mark" (spoken punctuation on, only the commas I dictate on);
     - "Sometimes" (spoken punctuation on);
     - "I just talk; punctuate for me" (spoken punctuation off).
   - **Spoken formatting:** "new paragraph", "new line", quotes, numbered items.
   - **What you mostly dictate:** letters, short messages to staff, examination notes,
     results. This picks the reading texts and the vocabulary topics.
4. **Where the text goes.**
   - Copy at Stop, then paste with Ctrl+V.
   - Paste automatically at Stop.
   - Type into my document as I talk: slightly less accurate (2.9% vs 2.4%), text every
     few seconds.
5. **Start and stop.** Key, hold-to-talk or toggle, mouse button, then "press it now" to
   check that it works.
6. **Your usual medications** (optional). A box to paste the list into, saved to the user's
   `my_medications.txt`, with one line explaining why it helps.
7. **Practise and tune** (optional). See below.
8. **Done.** What was set, with every changed option listed. The same choices are in Options.

## Tuning to your voice

### The reading

- **The texts.** About 4–5 minutes in all, every person and value invented:
  - three short messages;
  - one examination note;
  - one results comment;
  - one letter with paragraphs, a heading and a numbered list;
  - one medication paragraph made from the person's own usual-medications list (their drug
    names, invented doses).

  Each text is stored once in its written form. `spoken_form()` produces the version to
  read, with or without the marks spoken, depending on page 3.
- **Tune and check.** Every text is marked in advance either for tuning (about five) or for
  checking (about three). The checking texts are never used to choose a setting; they only
  measure the result. The project already follows this rule ("mark calibration and
  validation utterances before examining outputs").
- **Recording.** Recordings go through the app's own microphone path (gain, ready
  microphone, pre-roll), so they match real use. They are saved as 16 kHz WAV under
  `%APPDATA%\MyTranscribe\tuning\<date>\`, about 2 MB a minute.
- **Reading slips.** People misread. After each text, the wizard shows what was heard with
  the differences marked, and offers three choices:
  - Next;
  - Read it again;
  - I said it differently. The person clicks a marked word to accept what was heard as
    what they said.

  This makes the reference what the person actually said, which matches the project's rule
  that the human-confirmed reading is the truth. If more than about a third of the words
  differ, the wizard suggests reading it again: the wrong microphone or a lot of noise is
  more likely than the model.
- **The baseline is free.** The app transcribes while the person reads, with the settings
  from pages 1–6. That is the "before" score.

### The search

It runs in the background with a progress bar, can be cancelled, and has three stages:

- **A. Text-only choices, on the saved raw text (milliseconds each).** Spoken punctuation
  on/off, only the commas I dictate, medical clean-up on/off, lenient commands. No new
  decoding is needed.
- **B. Choices that change what Whisper hears, which need a re-decode.** Usual medications in
  the prompt or not, pause-aware dictation on or off, and the 15 s windows if they chose
  typing as they talk (to show the real cost for their voice).
  - **On a 6 GB card:** large-v3 ran at about a tenth of real time in the October tests on
    the GTX 1660 Ti. So one pass over 5 minutes of reading takes roughly 30–40 seconds, and
    3–4 variants take 2–3 minutes. This is an estimate, to be timed on the 1060.
  - **Processor only:** about half real time, so stage B is limited to one variant.
- **C. Personal word fixes.** A word heard wrong the same way in two places, or once if
  what was heard is not a real word and the intended word is a medical term from the text,
  becomes a candidate `heard => meant` rule. A rule is kept only if all of these hold:
  - it fixes at least one error and causes none on all the readings;
  - its "heard" side is not an ordinary English word (word frequency check) and not a real
    drug name;
  - the person approves it.

### Deciding

A change is adopted only if all of these hold:

1. **Better on the tuning texts by a real margin.** At least 2 fewer word errors and at least
   a tenth fewer. On about 600 words, one word either way is noise.
2. **No worse on the checking texts.**
3. **No new clinical error:** no drug name, number, dose, unit, frequency, negation or layout
   that was right and is now wrong. This is the project's existing rule for promoting any
   change.
4. **Defaults win ties.**

The result page says it plainly, for example: "On the three checking texts (210 words):
9 word errors before, 6 after. Changed: spoken punctuation on, because you said 34 marks;
2 word fixes added." It also warns that on so few words a difference of two or three is
within chance.

### Repeating it

- **Read another set** adds a different group of texts. Readings are pooled across sessions,
  so each round has more to go on, and the checking texts stay separate.
- **Re-tune with my saved readings** runs the search again without reading anything. This
  is useful after an app update that changes defaults, or when a new option exists.

## Speaking naturally: letters formatted for you

This is a new feature and is not built yet. Today, a person who does not say the marks gets
Whisper's own sentence punctuation, which is good. Paragraphs, the salutation line, headings
and lists come only from spoken commands, so "just talk and it formats my letter" does not
work yet.

Plan: a letter-layout step made of rules, measured like everything else.

- **Salutation and sign-off.** "Dear Dr. X," goes on its own line with a blank line after it.
  "Kind regards," or "Yours sincerely," starts a new paragraph.
- **Headings.** A known heading at the start of a sentence ("Impression:", "Plan:",
  "Medications:", "History:") starts a new paragraph.
- **A long pause between sentences starts a new paragraph.** People's pauses differ a lot,
  so the threshold is personal. It is the cleanest example of tuning to a voice. The
  reading's letter has known paragraph breaks, so the wizard measures the person's pauses
  at those breaks and inside paragraphs, then picks the length that separates them.
  The word timings are already computed by the pause-aware pipeline.
- **Before it is offered,** it needs test material: letters read without dictated marks
  (the owner, plus later testers), scored with the existing layout checks (`format_ok`,
  `command_hits`). Synthetic voices are no use for the pause threshold, because their pauses
  are machine-made.

## Does it need an LLM or a coding agent?

Not for this plan:

- **The search space is small and discrete.** Plain code can try every option, explain
  each change and undo it.
- **Memory.** Large-v3 already uses about 3.7 GB of a 6 GB card, and a useful local language
  model would need another 2–5 GB.
- **Clinical risk.** A model that rewrites text can change a clinical word without anyone
  noticing. Every change this project makes is checked against that.

Where one could help later is the layout of naturally spoken letters: paragraphs and
headings. If that is tried, the model may only add line breaks and punctuation. The app
compares the words before and after, and if any word differs, it uses the rule-based layout
instead. That is phase 5, an experiment.

On the developer side, a tester could choose to export a numbers-only tuning report (no
audio, no text). Reports like that, collected through the tester feedback route, would show
which defaults to change for everyone. Claude can analyse them offline.

## Running it again

- **First start.** The wizard opens when the settings file has no `setup_version`, so only
  new installs see it. An existing settings file (the owner's) is never forced through it.
- **From Options.**
  - **Run setup again…** opens with every page filled in from the current settings.
  - **Tune to my voice…** goes straight to the reading.
  - **Check my microphone…** runs page 2 on its own.
- **Undo.** Each finished wizard saves the settings it replaced
  (`settings.before-<date>.json`) and the list of what it changed. Options → **Undo last
  tuning** restores them. Approved word fixes are written in a marked block of
  `corrections.txt`, so they can be removed together.

## Data and privacy

- **What is recorded and where.** The texts are fictional, but the recordings are the
  person's voice. They stay in `%APPDATA%\MyTranscribe\tuning\` and are never sent anywhere
  (about 10 MB per 5-minute set).
- **Deleting.** There is a **Delete my readings** button. A person can also choose not to
  keep the readings, in which case re-tuning means reading again.
- **Reading only the text shown.** The reading page says to read only the text shown,
  because ad-libbing could put real patient details in a recording.
- **Logs.** The log keeps counts and timings only, as now.

## Code layout (proposal)

- `src/setup_wizard.py`: the wizard (Qt `QWizard`), one class per page.
- `src/tuning/`:
  - `sets.py`: reading texts, and `spoken_form()` moved here from `validation_tool.py`;
  - `session.py`: recording, saving and the session manifest;
  - `replay.py`: `FileMic` and `run_pipeline` moved here from `dictation_reliability.py`,
    so the app and the scripts share one copy;
  - `score.py`: alignment, word errors, layout, and the clinical-field checks;
  - `search.py`: stages A–C and the decision rule;
  - `word_fixes.py`: proposing word-fix rules and checking them.
- `src/tuning/sets/en_v1.txt`: the fictional reading texts, each marked for tuning or
  checking.
- `settings.py`: new fields `input_device`, `setup_version`, `last_tuning`. The stream
  factory opens the chosen device and falls back to the default if it is gone.
- The scripts keep importing from `src`, so there is one copy of the replay and scoring
  code.
- Tests:
  - the wizard flow with a fake engine;
  - the decision rule, including ties and a new drug or number error;
  - the guards on word-fix rules;
  - settings migration, including that an existing file skips the wizard;
  - falling back when the chosen microphone is missing.

## How we will know tuning helps before testers see it

Test the method itself offline, on material we already have:

1. **Modulate synthetic voices.** There are 28 voices in 6 recording conditions. Treat each
   voice and condition as a separate "user": tune on some of that voice's notes and check on
   its others, against the defaults. This shows whether tuning helps, does nothing, or
   overfits. Synthetic voices are fine for testing the method, but not for an accuracy claim.
2. **The owner's corpus.** Tune on the development recordings and check on the held-out ones.
   That split already exists.
3. **The owner reads the wizard's own texts** once in each punctuation mode.
4. **Corti is not used.** It is for evaluation only and rationed, and tuning is per person
   anyway.

**What success means:**

- on the checking material, tuning never makes any synthetic "user" worse by more than noise;
- on average it helps;
- it never adds an error in a drug name, number, dose, unit, frequency or negation.

If tuning cannot beat good questions plus the medications list, the wizard ships with the
questions, the microphone check and the before/after score only. That would still be
worth having.

## Synthetic voices for testing (terms checked 2026-11-18)

**What they would be used for.** More voices make better test material for three things:

- checking the tuning method (phase 3);
- letters dictated without spoken marks (phase 4);
- trying the wizard's reading texts end to end.

**Their limits.** A computer voice is not a clinician. It mispronounces some drug names, and its
pauses are generated, so it cannot set the personal paragraph-pause length.

**Cloud voice services: not usable as things stand.** Each of these companies also sells speech
recognition, and each one's terms restrict using its output for work like ours. That holds
whether or not the project is commercial.

| Service | What its terms say | Reading |
|---|---|---|
| ElevenLabs | **Prohibited Use Policy** (updated 9 Oct 2026, section 12) bans using its services or output "to develop, train, fine-tune, or improve any AI model or service", or putting output in a dataset for those purposes, "except as expressly permitted"; and using them "to research or develop products or services that compete with ours". **Terms of service:** a free plan is "non-commercial purposes" only, and no health information may be sent. | Tuning our pipeline on it is improving an AI service. A public test set also falls under the dataset clause. A paid plan does not lift either clause. Not usable without written permission. |
| OpenAI TTS | **Terms of use:** no use of output to develop models that compete with OpenAI. **TTS guide:** says the usage policies require telling listeners that the voice is AI-generated, and that the current TTS models shut down on 6 Jan 2027. The usage policy page itself could not be read. | Unclear, and the same competing-product risk. |
| Google Cloud TTS | **Service Specific Terms**, section 17: no use of an AI/ML service or its output "to develop a similar or competing product or service". Whether Text-to-Speech counts as an AI/ML service there was not confirmed. | Unclear. |
| Azure Speech | **Product Terms** (an excerpt, not read in full): no use of the services or their data "to create, train, or improve" a similar or competing product or service. | Unclear. |

**Open-weight voices that run on this PC: usable.** There are no service terms, the voices run
offline, the output can be published, and nothing is sent anywhere. All fit the RTX 4070 Ti
SUPER, and Kokoro also runs on a processor.

| Model | Licence of the weights | Notes |
|---|---|---|
| Kokoro-82M | Apache-2.0 | 54 preset voices across 8 languages, American and British English among them; small and fast. Good for many voices quickly. |
| Chatterbox (Resemble AI) | MIT | 0.5B. Copies a voice from a short clip. Output carries an inaudible watermark. Copy only voices whose owners agree, such as the owner's or a tester's. |
| Orpheus 3B | Apache-2.0 | Gated on Hugging Face, so it needs the user's own account. Natural intonation; English. |
| Dia 1.6B | Apache-2.0 | About 10 GB of graphics memory; made for dialogue; English. |
| XTTS-v2, F5-TTS | Non-commercial (Coqui Public Model License; CC BY-NC) | Avoid, to keep the project's licences simple. |

**Proposal.** Use Kokoro for breadth of voices, and Chatterbox or Orpheus for realism. Pass
the audio through the existing microphone and room simulations in
`scripts/make_test_dictation.py`. Keep Modulate's 28 voices (CC BY 4.0). Each model download
needs the owner's go-ahead.

ElevenLabs could be used only with written permission. The request would cover non-commercial
evaluation and tuning of an open-source dictation app, with fictional scripts only.

These are readings of the published terms, not legal advice.

## Phases

1. **Questions, microphone check, re-run from Options.** No tuning. Includes choosing the
   microphone and first-start detection. Small and low-risk, and could reach testers soon.
   **Built 2026-11-18.**
2. **Practise reading.** Before/after score, reading-slip review, the usual-medications page,
   and proposed word fixes with approval.
3. **Automatic tuning search** (stages A–C and the decision rule), after the offline
   validation above passes.
4. **Natural-speech letter layout.** Build it, measure it, then offer it in the wizard.
5. **Optional experiment:** a local language model for letter layout, under the word-identity
   check.

Each phase is its own commit, so it can be rolled back on its own. Each goes to
`dictation/personal-english` and is then copied to `release/tester-preview`.

## Decisions for the owner

1. **Reading length.** About 5 minutes, or also a 2-minute short version?
2. **Keep readings for re-tuning by default,** or delete them after tuning?
3. **Choosing a microphone in the app** (new): add it in phase 1?
4. **Natural-speech letter layout** (phase 4): build it?
5. **First build:** for testers, or both builds together? The four-language build needs
   reading texts in each language.

## Risks

- **Too little material.** 600 words is little. The tune/check split, the minimum margin
  and "defaults win ties" limit how far the tuning can chase noise.
- **Reading slips teaching wrong fixes.** Handled by the slip review, the two-occurrence
  rule and the person's approval.
- **Tuning in a quiet office, dictating in a noisy clinic.** The wizard suggests tuning
  where they dictate, and the microphone check is quick to run again.
- **Slow hardware.** On a computer without a suitable graphics card, tuning takes longer.
  Progress is shown, it can be cancelled, and the "before" settings stay in place.
- **Surprises.** Every change is listed on the last page and can be undone in one click.

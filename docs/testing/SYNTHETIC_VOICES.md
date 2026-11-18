# Synthetic voice test set: plan

**Status (2026-11-18):**
- **Scripts:** the English scripts are written and checked by `tests/test_synthetic_set.py`.
  The owner has not reviewed them yet.
- **Generator:** `scripts/synth_voices.py` is built and tested, with no network in the tests.
- **Audio:** all 480 clips made and checked. 479 say their text in full; the one exception
  is recorded below.

Terms and principles are in [README.md](README.md).

## Purpose

1. **Choose the settings** behind each setup-wizard answer.
2. **Check the tuning method:** each voice reading in one style acts as one pseudo-user.
3. **Regression-test the rules** across accents. One example: "full stop" and "period" must
   both work.

Not for accuracy claims or training.

## Voices: 12 OpenAI voices

The panel is `validation/synthetic_voices_en_v1.json`.

**One engine for now.** Only an OpenAI key is available, so all 12 come from OpenAI
(`gpt-4o-mini-tts`). The plan was 6 from Amazon as well, so that no result rests on one
synthesiser's quirks. A second engine, Amazon or a local open model, is still to be added.
Until then, a finding that holds for only some voices is treated with care.

The accents are those of the clinicians likely to use the app: Canadian, French-Canadian and
other Commonwealth English, plus speakers educated abroad. That makes 6 women and 6 men, at
mixed paces.

Each accent comes from an instruction and is unverified until heard. A voice that sounds like
a caricature, or whose accent drifts, is replaced by the spare (`fable`). "Sex" is how the
voice sounds; OpenAI does not state it.

Two whole voices are held out and used only for the final check.

| Id | Voice | Accent | Sex | Pace | Mark word | Home mic | Split |
|---|---|---|---|---|---|---|---|
| V01 | `marin` | Canadian | F | normal | period | headset | dev |
| V02 | `cedar` | Canadian | M | fast | period | conference | dev |
| V03 | `coral` | French-Canadian | F | normal | period | noisy | dev |
| V04 | `ash` | Nigerian | M | normal | full stop | headset | dev |
| V05 | `sage` | Arabic-speaking | F | slow | period | conference | dev |
| V06 | `onyx` | Mandarin-speaking | M | normal | period | noisy | **held** |
| V07 | `nova` | Southern British | F | normal | full stop | conference | dev |
| V08 | `ballad` | Northern English | M | slow | full stop | noisy | dev |
| V09 | `echo` | Australian | M | fast | full stop | headset | dev |
| V10 | `verse` | Indian | M | normal | full stop | conference | dev |
| V11 | `shimmer` | Irish | F | normal | full stop | noisy | dev |
| V12 | `alloy` | South African | F | normal | full stop | headset | **held** |

## Making the audio

1. **Save the key once,** encrypted for this Windows account, in your own PowerShell window.
   It is never pasted into chat or written in the repository.

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\synth_voices_key.ps1
   ```

   Add `-Status` to check whether a key is saved. The file is
   `results_1060/synthetic_voices/secrets/openai.dpapi`.

2. **See the cost** with `python scripts/synth_voices.py plan`. No network.
3. **Make the audio** with `python scripts/synth_voices.py make --go`.
   - It stops before starting if the estimate is over `--budget-usd`, which defaults to $5.
   - It skips clips already made.
   - It writes 24 kHz originals and 16 kHz copies to `results_1060/synthetic_voices/en_v1/`.
   - `manifest.jsonl` records the voice, instruction, exact text, length, checksum and date
     for each clip.

4. **Check that each voice said its text** with `python scripts/synth_voices.py check`, then
   `reject`, then `make --go` again.
   - Each clip is transcribed with the local Whisper model and compared with what the voice
     was given.
   - A run of 3 or more content words skipped or added is flagged. Formatting differences
     ("15mg" for "15 milligrams") and command words do not count.
   - `reject` moves flagged clips aside, and `make` remakes them.
   - A recogniser error can cause a needless remake, at a cost of cents. A skip of fewer than
     3 words can go unnoticed.

What the voice is given is the spoken form of the script, with two changes:
- units are spelled out ("500 milligrams");
- a short pause follows each spoken command, as a dictating person's would.

**Pilot, 2026-11-18:** voices V01, V04 and V06 read e05, n02 and q02, giving 9 clips, 6.8
minutes, about $0.10.
- **Raw Whisper got 6.6% of words different from what was said,** mostly formatting ("3"
  heard as "three", "mg" for "milligrams"). The every-mark clip came out of the app's rules
  as correctly laid-out notes.
- **Marin skipped a letter's sign-off.** The instruction now asks the voice to read through to
  the last line, and the fidelity check above was added.
- **Two of three readings came out without the self-correction ("20 mg, sorry, 15 mg").**
  Self-corrections are now marked as said but not written, so the expected text is the
  corrected one.
- **The audio is kept in `en_v1_pilot/`.** The full set uses the new instruction throughout.

**Full run, 2026-11-18:** 480 clips, 284 minutes, about $4.26 at OpenAI's estimate.
- **What the first check flagged:** 55 clips.
  - **Five were the check's own errors.** Whisper invented phrases at the end ("thanks for
    watching"), wrote a number as words, or misheard a drug name. The check now pads each clip
    with a second of silence, ignores those invented phrases and number spelling, and judges
    each clip against the exact text it was given.
- **The other 50 were real:** the voice stopped before the last line.
  - Most were a letter's sign-off name ("Dr. Priya Raman"), which voices treat like a
    signature block.
  - The rest were a script's last sentence.
- **For the remakes,** the name is given to the voice as a sentence ("Doctor Priya Raman.").
- **Remakes:** three rounds left 12, then 5, then 1 clip flagged. They added 40, 11 and
  5 minutes, about $0.84, so the full run came to **about $5.10 by the estimate** ($5.20 with
  the pilot). The actual charge is on the owner's OpenAI usage page.
- **The one clip left:** V08 (`ballad`) reading e02 ends before its sign-off in all three
  tries. Rule for the suite: a clip whose only flag is a missing sign-off is scored without
  that sign-off; any other flagged clip is left out. Flags are in `fidelity.jsonl`.
- **Sampler for listening:** each voice reading n02 is in the owner's Google Drive
  ("MyTranscribe validation/synthetic voice samples"), private to the owner.

OpenAI's current voice models shut down on 6 Jan 2027, so the originals are kept: they
cannot be remade after that date.

## Dictation styles: 5 guidelines, not fixed rules

| Style | What the speaker says | Content | Wizard answer it tests |
|---|---|---|---|
| S1 Every mark | every mark and layout word: "comma", "full stop" or "period", "new paragraph", "number one" | consult letters with a list | "I say every mark" |
| S2 Sentence marks | sentence ends and paragraphs, no commas | letters, examination notes | "Sometimes" |
| S3 Layout only | natural sentences, plus "new paragraph" and "next line" | letters | "I just talk", with commands (today's default) |
| S4 Just talk | no marks and no commands; some "um"s and one self-correction per script | letters, staff messages | "I just talk"; the target of the phase 4 letter layout |
| S5 Quick notes | fragments, numbers and units, headings said as words, sentence marks | examination notes, results, staff messages | content stress test, any answer |

Every voice reads every style: 60 pseudo-users.

## Scripts

- **Where:** `validation/synthetic_set_en_v1.txt`, 40 scripts and about 2,760 words.
  - The text is public.
  - The audio will stay in `results_1060/synthetic_voices/`. A manifest will record the
    engine, model, voice, instruction and date for each clip.
- **New texts.** v1 and v2 are not used, because they back the published figures. The test
  checks that no patient and no sentence is shared with them.
- **Per style:** 8 scripts, 450 to 640 words (quick notes are the densest). Each is marked in
  advance: 5 for tuning, 3 for checking, and the checking items mix kinds.
- **One written form per script.** `spoken_form()` in `src/tuning/sets.py` generates what each
  style says, with "period" or "full stop". Braces mark words that are said but not written:
  a hesitation (`{um}`), or a self-correction (`{20 mg, sorry,} 15 mg`), whose written form
  is the corrected text.
- **Every script has** a drug with a dose and a negation. **The set as a whole covers:**
  - openings and sign-offs;
  - headings;
  - numbered lists;
  - readings such as 138/78;
  - percentages and questions;
  - a quotation;
  - semicolons;
  - self-corrections;
  - brand and generic drug names.
- **Checked by `tests/test_synthetic_set.py`:**
  - every rule above;
  - for each script, that the words, said with every mark, turn back into exactly the
    written text through the app's own rules;
  - in the script's own style, the same for its words and layout.

  Another language adds its set file and one entry in that test.
- **What writing them found in the app's rules:**
  - **Fixed on 2026-11-18:**
    - *"A1c" after a dictated comma* was lower-cased to "a1c".
    - *"New line" before "On examination"* was read as a noun phrase when the model wrote no
      punctuation.
  - **Still open:**
    - *A mid-sentence quote* is converted only when punctuation sets it off. It is item e03,
      listed as a known gap in the test.
    - *A speaker who says no marks* gets "Dear Dr. X." with a full stop. This is for the
      phase 4 letter layout.
- **Before audio is made,** the generator must spell units out for the voices (mg as
  milligrams, mmol/L as millimoles per litre). The written form keeps the abbreviations.
- **If decisions come out close,** a second pool of 8 scripts per style is added, read by half
  the voices each, for more variety of content.

## Size and cost (current list prices)

- **Volume:** each voice reads all 40 scripts. That is about 3,000 spoken words with the
  marks, or about 22 minutes per voice, so about 4.3 hours for 12 voices.
- **Cost, all 12 voices from OpenAI:** about 4.3 hours at its earlier estimate of 1.5 cents a
  minute is **about $4**. It bills $12 per million audio tokens; the per-minute figure is
  unverified. `synth_voices.py plan` prints the current estimate.
- **Amazon, if added later:** about $3.60 for 6 voices, at $30 per million characters
  (generative).
- **Each clip is used twice:** clean, and through its voice's home microphone (simulated by
  `make_test_dictation.py`). Both are made locally at no cost.

## Settings suite

This builds on `scripts/dictation_reliability.py`: its `PROFILES` (named settings) and
`run_pipeline` (the app's own pipeline).

**1. Wizard answers.** One profile per answer:

| Profile | Spoken punctuation | Only dictated commas | Commands | Existing profile |
|---|---|---|---|---|
| `every` | on | on | on | `personal` |
| `some` | on | off | on | `candidate_full` |
| `talk` | off | — | on | new: `candidate` plus medical clean-up |

All three have pause-aware dictation and medical clean-up on.

Each profile is also run in three variants:
- `+live`: 15-second windows, for typing as you talk;
- `-fixes`: medical clean-up off;
- `+meds`: a usual-medications list in the prompt.

**2. Mismatch table.** Every style is run under every profile, a 5 × 3 grid. The matching
profile should win. The other cells show which wrong wizard answer costs the most, and so
whether the wizard must check the reading ("did they actually say the marks?").

**3. Tuning-method check.** For each pseudo-user, stages A–C of the
[wizard plan](../settings/SETUP_WIZARD_PLAN.md#the-search) are run on the 5 tuning scripts.
The result is scored on the 3 checking scripts, against the wizard profile alone.

**Decoding is done once per audio-changing setting:**
- pause-aware on or off;
- at Stop or typing as you talk;
- medications in the prompt or not.

The text-only choices are re-scored from the saved text, without the graphics card.

**Scores:**
- word errors;
- marks missing and added;
- layout correct;
- leftover command words;
- clinical-field errors.

They are reported by style, voice, engine and microphone, as paired differences per clip.

**Changing a default needs all of these:**
- it wins on the dev voices by the margin in the settings rules;
- it is no worse beyond noise for any accent;
- it adds no clinical error;
- it is then confirmed on the held voices and on the owner's real recordings.

## Steps

1. **Write the scripts.** Drafted 2026-11-18; the owner reviews them.
2. **Listen.** On 2026-11-18 the owner chose to skip listening first. A voice whose accent
   fails is replaced after the pilot.
3. **Generate the audio** ([Making the audio](#making-the-audio)).
   - The owner approved it on 2026-11-18, with their own OpenAI key and the $5 cap.
   - It was allowed under the terms in force that day (see [README.md](README.md)).
   - It starts with a small pilot to check the voices and the text before the full run.
4. **Build the suite runner,** run it, and write up the results in `docs/optimization/`.

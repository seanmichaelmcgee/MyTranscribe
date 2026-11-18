# Settings suite: the first round of app-wide fixes (2026-11-18)

The baseline ([2026-11-18-settings-suite-baseline.md](2026-11-18-settings-suite-baseline.md))
listed six candidate changes, A to F. The owner approved all of them, plus G: letter layout
for natural speech. This note says what was done for each one, and how it was measured.

**Material:**
- the 12-voice synthetic set (480 clips, dev voices shown);
- the owner's 47 real headset recordings: dictation with spoken layout commands, without
  dictated marks.

Synthetic results propose a change, and the real recordings decide it
([rules](../settings/README.md)).

## Results

Word errors %, dev voices, with the answer setup gives each style.

| Speaker style | Before | After |
|---|---|---|
| every mark | 1.41 | 1.18 |
| sentence marks | 0.71 | 0.71 |
| layout commands only | 1.89 | 1.28 |
| natural speech | 2.03 | 0.82 |
| quick notes | 2.01 | 1.21 |
| **all** | **1.57** (1.12 names free) | **1.04** (0.59 names free) |

**Clinical fields and layout:**

| | Before | After |
|---|---|---|
| Numbers | 23 of 2,800 | 7 |
| Negations | 2 of 750 | 1 |
| Drug names | 26 of 2,180 | 22 |
| Letters laid out right | 158 of 270 | 178 |

**Notes on these runs:**
- The "After" column uses fresh decodes, with every change below in place.
- The held-out voices come in at 1.16% (V06) and 1.05% (V12).
- Decoding ran at 17× real time.

**The owner's real recordings (47, 3,225 words, same settings):**
- Before today's text changes: 239 word errors.
- After them: 241 word errors.
- The only difference is one self-correction (see E below). Letters laid out right: 24/25
  both times. Commands: 110/114 both times, none added.

## What was done

| # | Change | Result |
|---|---|---|
| C | Hesitations ("um", "uh") removed from every English transcript, whatever the options | All 32 synthetic "um"s gone. "ER", "mm" and "uh-huh" are kept. |
| D | "minus 3.1" → "-3.1"; "1 gram" → "1 g", litres → L, other spelled units after a number | All 40 such errors gone. "units" is never shortened; "5 minus 3" and "plus or minus" stay. |
| E | Self-corrections: "20 mg, sorry, 15 mg" → "15 mg" (also "I mean", "correction", "or rather") | All synthetic self-corrections resolved. It fires only when both sides are the same kind of thing: an amount, a blood pressure, a spinal level, a side or a day. |
| F | Brand names became targets for the drug-name corrector ("Jardientz" → Jardiance); MoCA; FEV1/FVC | Drug-name errors 26 → 23 of 2,180. Vocabulary will keep growing. |
| G | Letter greeting and sign-off laid out when no layout command was said; "Dear Dr. X." → "Dear Dr. X," | Natural speech: 0 → 120 of 200 paragraph breaks, with none added wrongly |
| B | Spoken punctuation on for the natural-speech answer too | Owner's recordings: 7.50% → 7.47%, a tie. Synthetic: better for natural and layout-command speakers. |
| A | Recover more dropped layout commands | Not changed. See below. |

## E: the one change on real speech

One of the owner's scripts says "The hernia was left, correction, right inguinal. The final
recorded side is right." Its reference keeps the correction as said. The new rule writes
"The hernia was right inguinal", which counts as 2 errors against that reference. Whether a
corrected side should be resolved, or kept as said for the reader to see, is the owner's
call.

## A: why the app is unchanged

- **Most "lost" commands were never said.** In 43 synthetic clips, no command reached the
  text under any prompt. There, the audio where a command belongs holds no more sound than an
  ordinary pause between sentences (about 0.35 s; saying "new paragraph" takes about 0.7 s).
  The voices read the commands as pauses. That accounts for 220 of the 295 commands the
  baseline counted as lost.
- **The cause of the rest was the prompt.** Someone who says no marks gets a plain-letter
  example as Whisper's style prompt, and that example contains no commands.
- **Putting the commands in that example did not help real speech.** On the owner's
  recordings, commands stayed at 110/114 either way, and letters laid out right fell from 24/25
  to 22/25, one of them with a wrong list number. So it was not adopted.
- **What still needs real speech from other people:** the owner's recordings keep every command
  that is in the audio. The one recording that "lost" four is shorter than its script.

## G: why only the greeting and sign-off

- **Paragraphs inside a letter cannot be told from the words.** The plan is to use pauses,
  measured on real speech, because synthetic pauses are machine-made.
- **The owner's own letters keep the greeting on the first line** ("Dear Dr. Okafor, Thank you
  for seeing…") and end "Kind regards." while saying "new paragraph" elsewhere. So the
  automatic layout applies only when no layout command was said: whoever says the commands
  chooses the layout.

## B: the decision

- **On the owner's recordings,** spoken punctuation made no difference: 7.50% vs 7.47% word errors,
  letters laid out right 24/25 either way, and commands 110/114 with none added either way.
  No word was wrongly turned into a mark.
- **On the synthetic voices,** it helped natural speakers (0.90% → 0.82% with C–F in place) and
  layout-command speakers (1.72% → 1.28%), and it lost fewer numbers (4 of 480 against 12).
- **It also removes the cost of a wrong answer.** A natural speaker who does say "period" keeps
  the mark, instead of losing 12–24 points.
- **"Colon" the organ:** the existing rules keep "colon cancer" as words. The three synthetic
  ": , cancer" errors were made by the audio generator: it added a pause mark after "colon",
  which the voice read aloud as "comma". The generator is fixed for future audio.

## Left for later

- Paragraphs by pause, for natural speech: needs real recordings.
- More vocabulary, from testers' word-fix reports. Donepezil is still misheard by three
  accents.
- Names: the largest remaining source of errors (Sofia/Sophia alone is 40 of 346). Names are
  scored separately, and a per-user word list is the remedy.

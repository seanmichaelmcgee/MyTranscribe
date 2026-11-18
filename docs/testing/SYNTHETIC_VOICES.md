# Synthetic voice test set: plan

**Status (2026-11-18): planned.** No scripts are written and no audio has been made. The
owner listens to the voices first. Paid generation waits for the owner's go-ahead. Terms and
principles are in [README.md](README.md).

## Purpose

1. **Choose the settings** behind each setup-wizard answer.
2. **Check the tuning method:** each voice reading in one style acts as one pseudo-user.
3. **Regression-test the rules** across accents. One example: "full stop" and "period" must
   both work.

Not for accuracy claims or training.

## Voices: 12, a draft until the owner has listened

Two engines, so no result rests on one synthesiser's quirks.

The accents are those of the clinicians likely to use the app: Canadian, French-Canadian and
other Commonwealth English, plus speakers educated abroad. That makes 6 women and 6 men, at
mixed paces. OpenAI's accent comes from an instruction and is unverified: a voice that sounds
like a caricature, or whose accent drifts, is dropped.

One whole voice per engine is held out. It is used only for the final check.

| Id | Engine, voice | Accent | Sex | Pace | Mark word | Home mic | Split |
|---|---|---|---|---|---|---|---|
| O1 | OpenAI `marin` | Canadian | F | normal | period | headset | dev |
| O2 | OpenAI `cedar` | Canadian | M | fast | period | conference | dev |
| O3 | OpenAI `coral` | French-Canadian | F | normal | period | noisy | dev |
| O4 | OpenAI `ash` | Nigerian | M | normal | full stop | headset | dev |
| O5 | OpenAI `sage` | Arabic-speaking | F | slow | period | conference | dev |
| O6 | OpenAI `onyx` | Mandarin-speaking | M | normal | period | noisy | **held** |
| A1 | Amazon Amy (generative) | British | F | normal | full stop | conference | dev |
| A2 | Amazon Brian (generative) | British | M | slow | full stop | noisy | dev |
| A3 | Amazon Russell (generative) | Australian | M | fast | full stop | headset | dev |
| A4 | Amazon Arjun (generative) | Indian | M | normal | full stop | conference | dev |
| A5 | Amazon Niamh (generative) | Irish | F | normal | full stop | noisy | dev |
| A6 | Amazon Ayanda (generative) | South African | F | normal | full stop | headset | **held** |

**Spares, if a voice fails the listening test:**
- OpenAI: `alloy`, `ballad`, `echo`, `fable`, `nova`, `shimmer`, `verse`;
- Amazon: Olivia (Australian), Kajal (Indian), Aria (New Zealand), Jasmine (Singaporean),
  Matthew or Ruth (US).

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

- **New texts.** Not v1 or v2, which back the published figures. Eight scripts per style,
  about 650 words (5 minutes) per style, marked in advance: 5 for tuning, 3 for checking.
- **One written form per script.** The spoken form for each style and mark word is generated
  from it. This needs `spoken_form()` to take a style and "full stop".
- **What each script contains:** at least one drug with a dose, numbers with units, and a
  negation. The set as a whole covers:
  - "Dear Dr. …" openings and sign-offs;
  - headings;
  - numbered lists;
  - readings such as 138/78;
  - brand and generic drug names.
- **Stored in** `validation/synthetic_v1/`. The text is public; the audio stays in
  `results_1060/synthetic_voices/` with a manifest that records the engine, model, voice,
  instruction and date for each clip.
- **If decisions come out close,** a second pool of 8 scripts per style is added, read by half
  the voices each, for more variety of content.

## Size and cost (current list prices)

- **Volume:** 12 voices × 5 styles × about 650 words is about 39,000 spoken words, or roughly
  4.6 hours of audio.
- **Amazon:** about 117,000 characters at $30 per million (generative) is **about $3.50**.
- **OpenAI:** about 140 minutes at its earlier estimate of 1.5 cents a minute is **about $2**.
  It bills $12 per million audio tokens; the per-minute figure is unverified.
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

## Steps, each with the owner's go-ahead

1. Write the scripts. Claude drafts them and the owner reviews.
2. The owner listens:
   - at [OpenAI.fm](https://www.openai.fm/): voice, accent instruction, a script;
   - to Amazon Polly in the AWS console.

   This fixes the 12 voices and their instructions.
3. Generate the audio, from 20 Nov 2026, with the owner's own API keys held in environment
   variables. This step costs money.
4. Build the suite runner, run it, and write up the results in `docs/optimization/`.

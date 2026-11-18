# Settings suite, milestone 1: baseline on 12 synthetic voices (2026-11-18)

**What was run:** 480 synthetic clips through the app's own pipeline under each wizard answer
to "how do you dictate punctuation":
- 12 OpenAI voices;
- 40 fictional scripts in 5 dictation styles;
- a new install, with no personal medications list or word fixes;
- Whisper large-v3 on an RTX 4070 Ti SUPER;
- decoding at 18× real time, 31 minutes in all.

Tool: `scripts/settings_suite.py`. Plan: [SETTINGS_SUITE.md](../settings/SETTINGS_SUITE.md).

These are synthetic voices: a guide to what to fix, not an accuracy claim.

## Results

Word errors %, dev voices. Rows are the speaker's style, columns the wizard answer, and *
marks the answer that matches the style.

| style | every mark | some marks | just talk (today's default) |
|---|---|---|---|
| every mark | **1.41*** | 1.41 | 14.93 |
| sentence marks | 0.71 | **0.71*** | 12.32 |
| layout commands only | 1.45 | 1.45 | **1.89*** |
| natural speech | 1.95 | 1.95 | **2.03*** |
| quick notes | 2.01 | **2.01*** | 23.81 |

**With the matching answer:**
- 1.57% word errors on the dev voices, 1.12% with names not counted;
- today's default answer for everyone gives 10.79%.

**By accent:** every voice comes in between 1.0% and 2.0%, the held-out voices included.
Synthetic speech is clear, so this says little about real accents.

## Findings

1. **The punctuation answer is still the largest factor.** A speaker who says the marks loses
   12 to 24 points under today's default.
2. **Spoken punctuation on is no worse for speakers who say no marks, and slightly better.**
   - Layout-style speakers: 1.45% against 1.89%. They also lost 4 numbers out of 480,
     against 12 with today's prompt.
   - Natural speech: 1.95% against 2.03%. "Heavy periods" was kept as words in all 12
     voices.

   The prompt with the dictated example seems to keep Whisper more literal.
3. **Spoken layout commands often never reach the text.** Whisper leaves out "new line" and
   "new paragraph" as if they were filler.
   - Kept: 72–79% in letters, 83–92% in notes and sentence-mark styles.
   - Mostly lost: "new paragraph", after a full stop and before a closing paragraph ("Thank
     you…", "Kind regards").
   - The pipeline's second listen into timing gaps rescued almost none here. On the owner's
     recordings it took commands from 49/56 to 56/56.
   - Result: layout is exactly right in 60 of 72 sentence-mark scripts, 50 of 72 every-mark
     scripts, and 16 of 60 layout-style scripts.
4. **Natural speech gets no paragraphs** (0 of 48). This is expected: it is the letter layout
   planned in phase 4.
5. **Small text gaps seen across all or most voices:**
   - "um" left in the text;
   - "minus 3.1" not written as "-3.1";
   - a self-correction ("20 mg, sorry, 15 mg") left as said;
   - "MoCA" written as "mocha";
   - "Jardiance" misspelled.
6. **Scoring artifacts, not errors:** name spellings, "1 gram" for "1 g", "lightheaded",
   "FEV1/FVC", "PR210". They are the same under every setting, so comparisons are
   unaffected.

## Candidate app-wide changes (none made; each needs the owner's approval)

| # | Change | Evidence here | Before shipping |
|---|---|---|---|
| A | Rescue more dropped commands: a better second listen where a command was likely said | About 200 commands lost out of about 1,190; layout right in 16/60 layout-style scripts | Measure on this set, then on the owner's corpus (no regression) |
| B | Spoken punctuation on by default, keeping the model's commas | Helps or ties for every style; avoids the 12–24 point loss | Check on the owner's real recordings, which have almost no dictated marks |
| C | Remove fillers ("um", "uh") | All 12 voices | Low risk |
| D | "minus 3.1" → "-3.1"; "1 gram" → "1 g" | All 12 voices | Low risk; matches the readings format |
| E | Self-correction: "X, sorry, Y" → "Y" for a value | 7–8 voices | Needs care; keep it narrow |
| F | Vocabulary: MoCA, Jardiance | 3–4 voices | Low risk |

**Next:** A is the largest and has a ready test bed in this set. B needs a real-speech check
first.

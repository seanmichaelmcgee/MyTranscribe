# Settings suite: mission and plan

Written 2026-11-18. This is a mission statement with milestones, not a specification. The
details are expected to change as each milestone's measurements come in.

## Mission

Anyone who installs MyTranscribe and spends **five minutes or less** on setup should get
dictation close to what the owner gets after months of tuning.

The settings suite is how that happens:
- it decides, from evidence, which settings each kind of user needs;
- it lets setup measure the few things that can only be learned from the user.

## What "close to the owner" means

**The owner's reference points:**
- 2.1% word errors reading consult letters;
- 7.0% on clinicians' dictation (Corti).

Those are the owner's voice and microphone, so they are a guide, not a target for every
voice.

**The working measure, for each new user:**

| Letter | Meaning |
|---|---|
| **D** | errors with the app's defaults |
| **S** | errors after setup |
| **O** | the best any available setting gets for that user |

Setup works when S is close to O:
- it recovers most of the distance from D to O (aim: 80% or more);
- it makes no user worse;
- it adds no clinical error.

What is left between O and the owner (accent, voice, recogniser limits) is measured and
reported, not hidden. Settings cannot fix it.

**Time:** the questions, the microphone check and the reading take 5 minutes at most,
processing included, on a 6 GB graphics card.

## Where the gains are (evidence so far)

| What | Effect measured |
|---|---|
| How the person dictates punctuation | The largest: 44.9% vs 14.2% word errors on Corti, depending on the setting. |
| Their usual medications | 2.44% → 1.22% on the owner's letters. |
| Microphone choice and level | Not yet measured; set by the microphone check. |
| Word fixes | For words a voice is consistently misheard on. |

Decoder settings are not on the list: beam size, silence detection, window length and prompt
rewrites all measured within noise. See [README.md](README.md).

So most of the optimising happens **before install**: defaults per wizard answer, chosen on
the test voices. Setup then only measures what cannot be known in advance: the person's
style, microphone and words.

## Two halves, one code

1. **Before install, by the developer.** The runner plays every test clip through the app's
   own pipeline under each candidate setting and scores it. It produces:
   - the defaults for each wizard answer;
   - what each wrong answer costs;
   - which signs in a short reading show the right answer.
2. **At setup, on the user's PC.** The user reads about 90 seconds of text, in their own
   style. Setup scores it with the same code, then:
   - confirms the style answer;
   - proposes word fixes;
   - chooses among the few settings that the evidence shows vary by person;
   - shows the before and after.

Both halves share one code base in `src/tuning/`, so what is tested is what users run.

## How we will know it works

- **Simulated setup for each of the 60 pseudo-users** (12 voices × 5 styles,
  [testing plan](../testing/SYNTHETIC_VOICES.md)). About 90 seconds of a pseudo-user's tuning
  scripts act as the reading; the checking scripts score the result. This gives D, S and O
  for every pseudo-user.
- **Held voices** (V06, V12) are used only at the end.
- **Real voices then confirm:** the owner's dev and held recordings, then testers'
  numbers-only reports.
- **The rules for changing a setting** in [README.md](README.md) apply throughout.

## Milestones

Each milestone ends with a measured result, a short write-up in `docs/optimization/` and a
commit.

1. **Baseline.** A runner and scoring; every clip under each wizard profile.
   - Results by style, accent and microphone.
   - The mismatch table: style × answer.
   - Clinical-field errors (drugs, numbers, negations).
2. **Defaults.** The settings for each wizard answer, chosen from milestone 1. Any change to
   an app default goes to the owner first.
3. **Setup, simulated.** The reading and the decisions setup makes from it, measured as D, S
   and O on the pseudo-users and improved until S is close to O.
4. **In the app.** The wizard's reading page and tuning, using the same code, timed on a 6 GB
   card.
5. **Real voices.** The owner, then testers.

## Left open on purpose

- **The reading's length and texts.** Start at about 90 seconds; shorten it if the
  simulation shows less is enough.
- **Which settings setup may change** beyond style, word fixes and medications. Milestone 3
  decides this.
- **Whether letter layout for natural speech belongs in setup** (phase 4 of the
  [wizard plan](SETUP_WIZARD_PLAN.md)).

## Guardrails

- No model is trained. Synthetic audio stays on this PC, and all texts are fictional.
- Setup never changes a setting without showing the change and allowing undo.
- A user's readings stay on their own PC.

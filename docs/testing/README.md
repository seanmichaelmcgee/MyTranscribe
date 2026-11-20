# Testing development

What the app is tested with, where it lives, and the judgments behind it. How settings are
chosen from the results is in [../settings/](../settings/README.md).

## Where things are

- **Test texts (fictional, public):** `validation/`. Every person and value in them is
  invented.
  - Sets v1 and v2 are English; the es and fr sets are drafts.
  - `synthetic_set_en_v1.txt` holds the scripts for synthetic voices. Its rules are
    `tests/test_synthetic_set.py`.
  - `term_set_en_v1.txt` (2026-11-20) holds about 350 classical terms in short notes:
    eponyms, organisms, scores and drugs. `scripts/term_bench.py` has voices read it and checks
    each term on each model. Its rules are `tests/test_term_set.py`.
  - The set format and each way of dictating are in `src/tuning/sets.py`.
- **Audio (private, this PC only):** `results_1060/`, which git ignores. This holds
  recordings, synthetic audio and transcripts. None of it goes on GitHub.
- **Tools:** `scripts/` ([index](../../scripts/readme.md)).
  - `dictation_reliability.py` replays audio through the app's own pipeline under named
    settings.
  - `validation_tool.py` records and scores readings.
  - `make_test_dictation.py` simulates microphones and rooms.
  - `spoken_punctuation_tts.py`, `lang_reliability.py` and `modulate_benchmark.py` build and
    score synthetic sets.
- **Results:** [BENCHMARKS.md](../BENCHMARKS.md) and [optimization/](../optimization/).
- **Plans:** [SYNTHETIC_VOICES.md](SYNTHETIC_VOICES.md), the 12-voice test set.

## What each kind of material may decide

| Material | Real voice | May be used for | Never for |
|---|---|---|---|
| Owner's recordings, split dev / held | yes | tuning on dev, confirming on held | publishing |
| Validation sets v1, v2 (owner and testers reading) | yes | measuring accuracy | tuning: they back the published figures |
| Corti Med-Dictate (clinicians) | yes | evaluation only, rationed | tuning or training |
| Modulate synthetic dictation (CC BY 4.0) | no | checking methods, term recall | accuracy claims |
| Cloud voices (OpenAI, Amazon) | no | choosing candidate settings, checking the tuning method | training, publishing the audio, accuracy claims |
| Local voices (Windows, Piper, Kokoro) | no | regression tests for the rules, other languages | accuracy claims |

## Voice service terms

Read on **18 November 2026**; OpenAI's usage policy re-read on **20 November 2026**, before the
term-set batch, when the new version came into force as expected. This is our reading of the
terms, not legal advice; re-read them before each new batch and update the date. **Testing and tuning** here means: fictional
scripts are read by the voice, our local recogniser transcribes them, and the scores choose
settings. **Training** means any model learning from the audio, including fine-tuning.

| Service | Testing, tuning | Training | Why |
|---|---|---|---|
| OpenAI API voices | yes | no | **Services Agreement** (1 Jan 2026) bans using output to develop competing AI models. **Usage policy, version in force until 19 Nov 2026,** says nothing more. **Version from 20 Nov 2026** bans supplying training material for models meant as substitutes for OpenAI's, and names evaluation, benchmarking and product development as allowed. Listeners must be told the voice is AI. No health information. |
| Amazon Polly | yes | no | **AWS Service Terms** (17 Nov 2026), 50.5: no generating content for the express purpose of training a model. Amazon may keep the text sent to it; an opt-out exists. |
| Google Cloud TTS | no | no | Bans using it or its output to develop a similar or competing product. Its Speech-to-Text is similar to ours, and testing while building is developing. |
| ElevenLabs | no | no | Bans using output to improve any AI model or service, and to develop competing products. Neither a paid plan nor its nonprofit programme lifts this. |
| Azure Speech | unclear | no | Not read in full. |
| Open-weight voices run here (Kokoro Apache-2.0, Chatterbox MIT; Piper per voice) | yes | yes, within the licence | No service terms. Record each voice's licence when it is chosen. Avoid XTTS-v2 and F5-TTS, whose licences are non-commercial. |

How we came to this:
- **Being non-commercial changes nothing.** The clauses apply to everyone.
- **Paying more does not buy training rights.** No public plan offers them. Only a negotiated
  contract could.
- **The audio is never published.** This keeps clear of the dataset and "supplying training
  material" clauses.
- **Dates are recorded.** Each batch records the model, the voice and the date the terms were
  read. OpenAI's current voice models shut down on 6 Jan 2027, so their audio cannot be
  remade after that.

## Principles

1. **The written text is the truth.** Spoken forms are generated from it for each way of
   dictating.
2. **Evaluation texts stay out of tuning.** v1, v2 and Corti are measured on, never tuned on.
3. **Compare settings on the same audio.** Comparisons are paired, so the number of distinct
   scripts, not the number of clips, is the sample size.
4. **Hold out whole voices,** not just sentences. The question is how a new user fares.
5. **Mark tune and check items before looking** at any result.
6. **Synthetic audio proposes; real speech confirms.** A synthetic word error rate is never
   quoted as accuracy.
7. **Clinical fields are scored on their own:** drug, number, dose, unit, frequency, negation
   and layout. Any new error in one blocks a change.

## Another language

The same rules apply. In addition:
- write the scripts in the language, with a clinician who speaks it reviewing them;
- add the language to `FEATURES` in `tests/test_synthetic_set.py`, with what counts as a
  dose, a negation and so on;
- generate the spoken forms from its language pack;
- cover that language's regional accents with voices from at least two engines;
- check and date each engine's terms;
- re-measure rather than assume that English results carry over.

# Persistent personal dictation curriculum

The curriculum centers on the user's everyday headset, with normal and genuine
whispered readings. Today's phone files stay historical; new phone work and a
second microphone are optional transfer checks when relevant to actual use.

Each cycle retains fictional audio, a fixed intended reference, direct human
clarifications, accepted spellings and the exact engine/profile that produced
the output. The persistent local folder is `results_1060/personal_curriculum`.
Personal medication lists, preferences, feedback and full transcripts remain
ignored. The generic template and tools are versioned in Git.

## What adapts

- **Vocabulary:** canonical terms, generic/brand names and expressly accepted
  spellings, grouped into small topics. Frequency and actual failure count set
  priorities. Dictionary presence alone does not prove recognition.
- **Style:** user-approved paragraph/list/quotation and abbreviation conventions,
  independently recorded from acoustic vocabulary. Style samples must avoid
  reusable ages, lab results, drug doses and frequency examples that can be copied.
- **Corrections:** narrowly tested non-word repairs with whole-word boundaries and
  a unique intended match. Preserve real drug names, accepted variants, numbers,
  doses/units/frequencies and negation. An uncertain word remains visible.
- **Evaluation:** original literal scores plus a separately versioned accepted-
  spelling view. `dysdiadokinesia` and `dysdiadochokinesia` are equivalent under the
  user's explicit policy; `dysdiatokinesia` and `dysthytokinesia` remain distinct.

These are adaptation and evaluation assets. Model weights have not been updated.
A future fine-tuning experiment needs a larger reviewed recording/reference set,
an independent hold-out split, an explicit training method and deployment checks.
Neither fine-tuning nor a dictionary guarantees the correct clinical word: a
valid but wrong drug or inserted frequency is still an error. Recognition should
retain ordinary prose and detect uncertainty as well as spell medical terms.

## A short recurring lesson

Collect two or three short fictional examples plus one paragraph-style note,
first normally and then whispered at the same microphone position/settings.
Use isolated Start/Stop recordings for the short cases. Keep each session a few
minutes long and rotate topics rather than reading an entire medication list.

1. Start with current recurrent failures: HGB/eGFR identity and modifiers,
   accepted examination terms and negation, then medication identity/dose/unit/
   frequency tuples. Add the user's frequent medications and oncology vocabulary.
2. Vary surrounding wording, positive/negative assertions and fictional values.
   Include correctly spoken sound-alike drugs and ordinary words as safeguards.
   Labels such as a chemotherapy regimen require confirmed identity; a guessed
   canonical name must not enter a candidate vocabulary.
3. Mark calibration and validation utterances before examining outputs. Reserve
   new wording/session examples for validation; normal/whisper pairs and crops
   of one reading stay in the same split. Phone samples are outside this cycle.
4. Freeze one small candidate and its unchanged control. Compare the same saved
   PCM with source/model/settings fingerprints, inspect every clinical change,
   and check the older headset corpus. Preserve each failed attempt.
5. Promote only a measured improvement with no new silent drug, numeric, frequency,
   negation or formatting error. Keep vocabulary/style changes separate so a
   benefit or regression can be attributed. Store the version and rollback path.

## Working tools

`scripts/personal_curriculum.py` initializes once and retains edits on reopening.
Its `feedback` command appends human notes for review; feedback does not silently
change recognition or the accepted-spelling policy. Increment the local policy
version for approved changes and retain its prior snapshot and source authority.

```text
venv1060\Scripts\python.exe scripts\personal_curriculum.py init
venv1060\Scripts\python.exe scripts\personal_curriculum.py status
venv1060\Scripts\python.exe scripts\personal_curriculum.py export-candidate
```

The export produces a compatible, versioned vocabulary file in `candidates`.
It is not automatically activated. The existing `MYTRANSCRIBE_VOCAB_FILES`
mechanism can load a selected candidate in a separately labeled trial; the
ordinary app retains its current configuration until the candidate passes.
Adding many close variants can reduce the corrector's unique-match margin, so
accepted spellings also require correction-regression checks before activation.

The `evaluate` command accepts `--manifest`, `--run` and `--out`. It checks complete
run/source/audio/reference identities on the explicitly recorded run scope and
keeps literal and accepted-spelling scores side by side. Output/input artifacts
are never overwritten. A capture manifest may append later recordings; explicit
historical run scope is reconstructed and fingerprint-checked rather than pooling
unseen recordings or relabeling the old run. No expected reference is sent to ASR.

The first curriculum contains the saved normal/whisper headset pair and the user's
accepted spelling. Its medication inventory and lesson packet are kept in the
local folder, with unresolved names labeled pending clarification. This setup
does not install a scheduler or background trainer.

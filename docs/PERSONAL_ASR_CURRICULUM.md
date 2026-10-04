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

## Separating recognition errors from unclear recordings

Keep a clear reading and an ordinary fast or mumbled reading of the same short
fictional script, using the headset at the same position. Keep the original PCM.
The operator confirms actual spoken wording and any skips; the displayed script
is only intended wording until that confirmation. Record fast/mumbled delivery
separately from whispered speech. All paired readings belong to the same split.

Run the frozen local Whisper control before changing prompts, vocabulary or
decoding. Preserve raw recognition against spoken wording and formatted output
against the written reference. Review drug identity, dose, unit, frequency,
negation and paragraph commands separately from aggregate word error rate.
Level, clipping, silence and decoder confidence are diagnostic measurements;
none alone measures intelligibility or certifies a correct word.

An independent audio recognizer must hear the same original recording without
the reference, local transcript or a request to repair those words. The existing
`scripts/frontier_audio_queue.py` supports a blind OpenAI file-transcription
comparison. Only explicitly identified fictional development audio is eligible.
Use the existing queue and a selected job to skip historical phone audio:

```text
venv1060\Scripts\python.exe scripts\frontier_audio_queue.py --root <existing-queue> run --execute --id <saved-headset-job-id> --max-jobs 1
```

Missing authentication leaves the selected job waiting without uploading. A
completed selected job is never submitted again. An uncertain paid request
requires an explicit retry, and the original response remains immutable.

The optional `scripts/openrouter_audio_queue.py` uses OpenRouter's dedicated
audio transcription endpoint and a fixed `google/gemini-3.5-transcribe` model.
It shares the existing durable queue, but distinguishes jobs by model/protocol,
requires one selected identity, and uses only `OPENROUTER_API_KEY`. It does not
send the expected script, local transcript, vocabulary hints or clinical values.
The model is an independent comparator; its superiority on these recordings
has not been established. The saved result retains its usage and audio identity.
Protocol verified against [OpenRouter's transcription API](https://openrouter.ai/docs/api/api-reference/stt/create-transcription)
and [model documentation](https://openrouter.ai/google/gemini-3.5-transcribe) on
2026-10-04. The provider alias does not establish immutable model weights.

On Windows, run `scripts/openrouter_secret.ps1` to enter a key in a hidden prompt.
It saves a DPAPI-encrypted secret under the ignored personal curriculum folder,
bound to the current Windows account. It never receives a key as an argument or
prints it. `-Action Status` checks existence without revealing it. A later
`-Action Run -JobId <saved-headset-job-id>` decrypts it only for the selected
comparison process and restores the parent environment afterward. Saving the
key makes no network request. Never paste a key into chat or commit it.

If the independent recognizer recovers a confirmed word that local Whisper
misses, the information was recoverable by at least one recognizer. If both miss
it, the cause remains unresolved: it may be acoustic ambiguity, shared model
limitations or a mismatch between intended and actually spoken words. Human
listening adjudicates the disputed passage; record uncertain spans rather than
turning a model consensus into training truth. An unclear fast passage that is
recoverable in the matched clear reading suggests a delivery or capture issue,
but does not prove which microphone or processing stage caused it.

Use human-reviewed spoken references as ground truth. Treat stronger recognizers
as comparators, not a guaranteed accuracy ceiling. Keep ambiguous passages out
of adaptation targets until adjudicated, and preserve new recordings for held-out
evaluation. Change one adaptation at a time and retain the baseline and older
headset regression cases.

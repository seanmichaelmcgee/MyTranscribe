# Primary-care English dictation: optimization status

The goal remains a fast, accurate, local dictation application for this clinician,
including brief instructions/results, complex examination notes and paragraph
letters. Filling GPU memory is not an acceptance criterion; measured recognition
quality and finishing delay determine whether extra computation is worthwhile.

## Current evidence and remaining requirements

| Requirement | Evidence | Remaining work |
|---|---|---|
| English-only recognition | Production engine explicitly requests English transcription. | Preserve in runtime experiments and any future engine selection. |
| Medical vocabulary and ordinary words | Large-v3, 30-second chunks: 4.7% overall / 3.1% medical error on 30 saved fictional voice recordings. | New independent recordings; reused calibration scores do not prove general clinical accuracy. |
| Numbers, negation, formatting | Current calibration: no numeric-token flags, one negation flag, 30/30 format and list-number checks. | Review clinical meaning on new examples; token/count checks are incomplete semantic evidence. |
| Fast brief instructions | Short recordings flush immediately; paced replay medians approximately 1.0–1.5 seconds after Stop. | Measure interactive start/stop/copy/paste latency and test search settings without sacrificing critical words. |
| Longer paragraph letters | Three recorded letters improved from 7.2% to 4.0% WER with 30-second cuts. Dense personal prompts now respect the token budget and no longer count discarded prompt tokens against output. | More 30–60-second paragraphs and individualized style examples, evaluated on held-out material. |
| Quiet and whispered speech | Compact meter reports captured RMS/peak; application gain is unchanged. | Paired real normal/whisper recordings, device comparisons and silence/VAD sensitivity tests before adding gain. |
| Clear, simple controls | F9 hold, mouse forward toggle, visible recording light and compact level bar; UI tests and rendered checks. | User's interactive check with their microphone and target applications. |
| Local, inspectable operation | Production launcher forces offline model access. Audio capture stays in memory; results/models/environments are ignored. Experimental decoders remain outside the app. | Retain these properties through future changes; full host security is not established by unit tests. |
| Effective use of this GPU | GTX 1660 Ti, 6 GB, Turing; large-v3 CUDA with int8_float32. Earlier alternating tests favor this over int8_float16. | Measure accuracy/speed/memory together for alternatives; preserve exact precision/configuration labels. |

The [4 October comparison](overnight/2026-10-04-asr-optimization.md) records the
completed MedASR/Whisper work and current product calibration. The
[personal sample plan](VOICE_SAMPLE_PLAN.md) describes the independent recordings
needed for the still-unverified requirements. Prior overnight automations are paused.

## Next runtime comparison

The opt-in `scripts/whisper_runtime_trial.py` reuses the current app replay and
explicitly labels model hashes, adapter/source hashes, threads, beam, patience,
temperature and actual compute type. It refuses device/precision fallback and
source/model changes before publishing completion. Recognition receives waveform
and bundled prompts; references are used only for scoring.

Seven controls were compared on the same corpus: application baseline
(beam 5, patience 2, two threads), eight-thread control, beam 3/patience 2,
beam 2/patience 2, beam 3/patience 1, temperature zero only, and full float16.
These are calibration experiments, not new independent samples. Selection must
consider clinical errors and per-workflow formatting, not just aggregate WER.

The [completed runtime report](overnight/2026-10-04-whisper-runtime.md) retains
the existing default. Full FP16 was 5.47 times slower and slightly less accurate;
beam 3's short-paced benefit averaged about 28 ms and it lost a medical word in
a letter. Two/eight threads produced identical transcripts and nearly identical
compute time. The full matrix and paced A/B/A follow-up finished successfully.

Changing beam size can occur between recordings on the same loaded model.
Changing precision is a model-load operation; automatic switching would incur
loading latency or require separately resident models and a measured memory budget.
No automatic precision switch has been added.

The [personal prompt budget fix](overnight/2026-10-04-prompt-budget.md) closes a
verified long-style output truncation bug. All 425 tests pass; a fresh changed-source
replay preserves every raw/cleaned transcript and raw chunk across the 30 saved
recordings. The current calibration remains 4.7% overall / 3.1% medical error.
The dense-prompt diagnostic demonstrates the output limit, not clinical accuracy.

## Personal capture follow-up

The user's first new combined test worked in the app, with a moving meter and a
successful copy logged, but the ordinary launcher retained no replay audio.
No new ASR score is available from that session. The
[remote sample plan](REMOTE_SAMPLE_PLAN.md) provides a dedicated fictional-test
launcher that retains only started dictations, with normal/whisper and local/phone
labels, a combined option and the comparison runner's GPU lock. The ordinary
application still keeps clinical audio in memory. The archive and chime shutdown
change pass all 444 tests; fresh saved recordings are the next accuracy evidence.

The [first phone recording](overnight/2026-10-04-phone-010.md) now supplies those
three fictional workflows in one file. Continuous Whisper output scores 3.5%
written error after one explicit non-word spelling correction, with 17/17 target
terms. The prior 30 recordings retain 4.7% overall / 3.1% medical error in fresh
matched controls. This is calibration on one normal-voice phone recording;
whispering and headset transfer remain unverified.

An important failure remains: the isolated 2.88-second result snippet copies
values from the style example, although the continuous pass gets it right.
A five-second minimal-style policy was rejected because it worsened the earlier
corpus's medical error to 7.1%. The app retains its existing prompts and decoding.
The exact spelling rule does not repair this abbreviated-result failure.

The [quieter second phone file](overnight/2026-10-04-phone-011.md) decodes cleanly,
is about 2.85 dB lower, and is retained by the existing speech detector. Bypassing
that detector leaves the isolated Whisper transcripts unchanged. Medical content
errors remain, including a lost negative nystagmus sentence and exertional
misrecognized as vaginal. Scores against the unchanged scripts are provisional
until exact reading and the BP 132-versus-138 discrepancy are confirmed; the file
has not been established as genuine whispered speech.

The existing weaker MedASR LM improves the matched 20-second exam control to all
four target terms, with aggregate medical WER 11.8% to 5.9% but unchanged 13.3%
overall WER. A fresh paced inference run reproduces its output and finishes in
0.06/0.22/0.34 seconds for result/exam/letter. It still misses HGB and replaces the
letter age with a placeholder. Whisper remains the product, with no prompt,
decoder, gain or spelling-rule change from this follow-up.

## Structured accuracy program

The user requested a new Sol 6.1/high coordinator and five focused agents with
disk checkpoints. The [coordinator brief](optimization/2026-10-04-accuracy-program/ORCHESTRATOR.md)
defines prompt/copying, regression, MedASR, capture and evaluation workstreams,
acceptance criteria, a bounded initial matrix and recovery rules. All scratchpads,
full supplied transcripts and detailed experiment state stay local and ignored.

The user supplied separate Frontier AI transcriptions and then confirmed that the
BP differences were speaking variations correctly transcribed. The 011 138/78
versus intended 132/78 difference is not an ASR failure. Original intended-script
scores remain historical comparisons; the new program adds external-reference
agreement and human-adjudicated field checks. The user subsequently clarified
that the Frontier values match what was spoken: 132/78 in 010 and 138/78 in 011.
Both are human-adjudicated correct fields.
The remaining medical-word, negation and prompt-copying failures still need work.

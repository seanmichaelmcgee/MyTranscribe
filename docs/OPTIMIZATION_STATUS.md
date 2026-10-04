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
| Longer paragraph letters | Three recorded letters improved from 7.2% to 4.0% WER with 30-second cuts. | More 30–60-second paragraphs and individualized style examples, evaluated on held-out material. |
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

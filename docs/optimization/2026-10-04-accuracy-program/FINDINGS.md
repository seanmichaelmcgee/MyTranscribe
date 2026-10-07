# Completed initial accuracy program — 4 October 2026

**Reject the prompt candidate and retain the working transcription defaults.**
All five Sol 6.1/high workstreams completed. The fixed two-configuration experiment
finished with 38/38 entries per configuration. Removing names and numbers from
the style example stopped the copied values on both short phone results, but did
not produce correct lab content. It also damaged a quotation command in the
older headset corpus. No additional variants or conditional paced follow-up ran.
This is calibration evidence, not independent clinical validation.

The ownership, evidence policy and remaining avenues are in [SPEC.md](SPEC.md);
the immutable selection and gates are in [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md).

## Matched results and decision

Both configurations used the pinned large-v3 model, CUDA int8_float32,
beam5/patience2, two threads and the existing 30-second pause-aware replay route.
Model/runtime/source identities, effective PCM and pre-VAD chunk hashes matched.
No expected transcript, corrected clinical value or external reference entered
recognition. Scoring preserved the original historical references and added a
separate external-reference view. Crops and whole files are correlated views,
not independent samples and not pooled into an accuracy headline.

| Scope / cleaned reference | Baseline | Candidate |
|---|---:|---:|
| Older 30 clips, historical written errors | 25/536 (4.7%) | 27/536 (5.0%) |
| Older clips, medical substitutions/deletions | 3/98 (3.1%) | 3/98 (3.1%) |
| Older clips, common substitutions/deletions | 20/426 (4.7%) | 18/426 (4.2%) |
| Older clips, target terms | 89/94 | 89/94 |
| Older clips, formatting | 30/30 | 29/30 |
| 010 crops, external notation-normalized agreement errors | 9/112 (8.0%) | 4/112 (3.6%) |
| 011 crops, external notation-normalized agreement errors | 14/112 (12.5%) | 9/112 (8.0%) |
| 010 whole, external notation-normalized agreement errors | 2/120 (1.7%) | 5/120 (4.2%) |
| 011 whole, external notation-normalized agreement errors | 11/120 (9.2%) | 11/120 (9.2%) |

The medical/common breakdown omits insertion costs; the overall error count
includes them. An improved common-word subtotal therefore does not establish
overall preservation. Historical raw spoken errors stayed 87/634 for both
configurations, which likewise does not erase the cleaned formatting regression.
Literal external counts, historical phone-script scores, full edit alignments
and per-workflow denominators remain in the local paired review.

All 52 changed raw/cleaned views were inspected, including every insertion and
clinical-field change. The candidate still substitutes HbA1c/HGP for the short
HGB result; the quieter examination still loses the negative nystagmus assertion;
the letter still changes exertional to vaginal chest discomfort. It introduces
unrelated opening words on some views and changes an older quote command into
ordinary text. These failures outweigh the reduced copied-value count.

Both human-adjudicated BP values remain correct in all inspected A/B views:
010 **132/78**, 011 **138/78**. They are speaking variations, not ASR errors.
The earlier intended-script BP mismatch remains historical evidence only.
Other external words retain model-comparison provenance; no direct listening or
new human certification was performed. Ages, doses/frequencies and numeric
fields were reviewed without adding guessed replacements or suppression rules.

## What the five reviews established

| Workstream | Evidence and implication |
|---|---|
| Whisper prompt | The example survives prompt assembly; hotwords are equivalent first-window token input, not a constrained vocabulary. Confidence checks did not reliably detect copying. Do not silently delete a value merely because it matches a prompt. |
| Whisper regression | No new historical degradation was proved. Persistent vocabulary rotation changes 5/74 later reconstructed prompts, with no first-chunk differences. The historical integer replay roundtrip changes samples by at most one least-significant bit and shifts one pause cut by 30 ms; it is not sample-exact GUI capture. |
| MedASR decoder | Exhaustive toy CTC checks passed 300/300 across three blank positions. Cached top16/top64 comparisons changed 0/11 outputs. No decoder fix/default change was justified. Posterior overlap fusion remains an untested, separately specified avenue. |
| Audio capture | The quieter phone file is about 2.85 dB lower but passes the existing gate. Quiet frames are buffered. A uniform +3 dB clips both files; no gain/VAD change was justified. True whisper and transfer to the proposed microphones need independent capture. |
| Evaluation | Seventeen saved runs were source-checked; one stale-source artifact was excluded. All 34 historical raw/cleaned BP views agree with the human values. Finite field checks are review signals, not clinical entailment. |

The next evidence should be new independent fictional utterances, with actual
normal/whisper phonation and device metadata, followed by held-out validation.
The proposed capture packet and deferred experiments are specified in SPEC.

## Bounds, timing and verification

The original campaign window is **17:35:31–19:35:31 UTC**. The frozen initial phase
window is **18:07:13–18:37:13 UTC**; execution finished at **18:10:29 UTC**.
Sequential baseline/candidate child elapsed times were 87.97/86.19 seconds,
including their process work. GPU sampling peaked at 4,312 MiB and 70 C;
there was no thermal stop. Children exited and the exclusive lock was released.
These windows are evidence and must not be extended on resume.

There is **no new Stop-to-formatted-text latency measurement**. Single warm offline
compute observations are saved separately; they do not establish clinician
latency or a timing distribution. The conditional paced phase was correctly
skipped after the content/format gates failed.

The full required suite passes **470 tests** with Qt offscreen, including 19
offline queue/worker checks. It does not prove live clipboard/microphone behavior.
No production source, prompt, correction, device or precision setting changed.
The ordinary app was restored and logged **Ready**, using large-v3 CUDA
int8_float32 and the Logitech G533 input. No live dictation was performed here.

## Persistent external comparator and recovery

Tracked development tools provide a durable queue plus an explicitly launched,
bounded worker. They retain blind request/result provenance, copied audio hashes,
success deduplication, visible ambiguous-request recovery, fixed original session
deadlines/budgets, singleton locks and owned-child cleanup. The final offline
payload check also verifies the hash of the exact bytes packaged for upload.
That provenance completion occurred after inference and changes no ASR output;
the frozen inference plan/results remain historical identities.

The original chat's existing two jobs remain blocked on provider selection and
secure authentication, with **zero new requests/uploads**. No background uploader
or scheduler was started. End-to-end API access remains unverified. Reuse the
existing queue; do not recreate its jobs or overwrite pasted references:

```text
--root results_1060/accuracy_program_20261004/frontier_bridge/data
```

Exact local recovery root:

```text
C:\Users\smich\Documents\Transcription Trials\MyTranscribe\results_1060\accuracy_program_20261004
```

Read `state.json`, `events.jsonl`, `handoff_updates.jsonl` and
`orchestrator/status.json` first. Each `workers/<role>/findings.md` and status is
complete. The immutable A/B plan, outputs, telemetry and paired review are in
`experiments/prompt_ab_v1`; app restoration evidence is under `orchestrator`.
The external prototype's ownership/setup notes are `frontier_bridge/AGENT.md`
and `frontier_bridge/status.json`. Audio, full transcripts, queue data and detailed
notes remain ignored. Resume with provider/auth setup in the original chat or
new independent capture; do not rerun the completed matrix or restart its clocks.

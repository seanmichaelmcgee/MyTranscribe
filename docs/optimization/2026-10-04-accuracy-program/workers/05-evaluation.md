# Worker 05: reference reconciliation and clinical evaluation specification

Write only `results_1060/accuracy_program_20261004/workers/05-evaluation/`.
Read WORKER_COMMON.md and ACCEPTANCE.md. Inspect the frozen user-supplied Frontier
transcripts/provenance, original personal scripts, eval_metrics.py, score_asr_trial.py,
actual matching phone outputs and prior corpus score evidence. Run CPU-only
analysis/prototypes in your folder; do not change shared scripts or manifests.

Design and compute (where identities match) an additional external-reference
agreement view. Keep intended-script metrics and frozen old manifests intact.
Do not relabel old schema-1 inference with a new corpus hash. Independently supplied
formatted transcripts are not verbatim spoken/command references or certified
truth. Voice 011 BP 138/78 and the files' exam/examination variants should no longer
be treated as local-engine mistakes solely because the original script differed.

Read user_feedback.json and handoff_updates.jsonl: the user confirms the BP
differences were correctly transcribed speaking variations and clarifies that
Frontier got both values right. Effective spoken values are 132/78 for 010 and
138/78 for 011. Use these as human-adjudicated fields; the initial feedback's
132/72 is superseded by that human clarification and remains history only.

Define clinical-field equivalences before comparing outputs: BP slash/over,
age, dose/unit/frequency, HGB/eGFR, explicit negation and change status. Preserve
literal WER alongside semantic checks and review critical insertions that historical
medical/common rates omit. Names are ignored, eponyms are scored. Review numbered
and paragraph formatting with actual task intent, not only count matches.

Deliver a reference/provenance design, supplemental phone scorecard, proposed
acceptance and new held-out sample protocol, plus a small CPU implementation or
test fixture for clinical-field checks if useful. Explain tiny denominators,
correlated sections, repeated playback and unconfirmed whisper condition. Propose
separate local-reviewer/formatting evaluation that cannot hide acoustic errors or
infer unheard values. No clinical correctness guarantee and no external upload.

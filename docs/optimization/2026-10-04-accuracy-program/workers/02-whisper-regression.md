# Worker 02: historical and current Whisper degradation audit

Write only `results_1060/accuracy_program_20261004/workers/02-whisper-regression/`.
Read WORKER_COMMON.md and the earlier regression audit. Inspect relevant Git
history with read-only commands; do not check out or reset shared files.

Determine which remaining hypotheses could explain unintentional feature-related
degradation. Distinguish UI effects from capture loss, model/precision/search
changes, prompt/topic rotation, token cap, postprocessing, corrected-text feedback,
chunk boundaries, and GUI-versus-replay state. Audit whether the current harness
faithfully reproduces app behavior. Earlier matched controls found benefit from
cleanup and 30-second chunks; do not reassert the historical audit as a new result.

Deliver a ranked causal map and one minimal historical/current or feature-control
experiment that holds waveform, reference, scorer, model and runtime fixed. Give
exact candidate commits/code paths, expected signature in raw versus cleaned
text, confounders and rollback tests. CPU-only trace/fixture prototypes may live
in your folder. Prefer a falsifiable remaining question over a large ablation
rerun. No GPU, Git mutation, shared source edits or source-version relabeling.

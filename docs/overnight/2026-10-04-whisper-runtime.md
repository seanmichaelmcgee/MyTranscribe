# Whisper runtime controls — 4 October 2026

## Decision supported by the completed matrix

Keep large-v3, CUDA, **int8_float32, beam 5, patience 2, 30-second chunks and
two CPU threads**. None of the seven runtime controls established a better
accuracy/latency tradeoff for the clinician's complete workflow. This is a
calibration finding on 30 reused fictional voice recordings, not proof of
accuracy on new clinical dictation.

| Runtime control | Overall WER | Medical WER | Common WER | Clinical term recall | Format / numbering | Numeric / negation flags | Total compute |
|---|---:|---:|---:|---:|---|---|---:|
| Application: INT8/f32, beam 5, patience 2, threads 2 | 4.7% | 3.1% | 4.7% | 94.7% | 30/30 / 30/30 | 0 / 1 | 40.81 s |
| Same, threads 8 | 4.7% | 3.1% | 4.7% | 94.7% | 30/30 / 30/30 | 0 / 1 | 40.71 s |
| Same, beam 3, patience 2 | 4.9% | 4.1% | 4.7% | 93.6% | 30/30 / 30/30 | 0 / 1 | 37.52 s |
| Same, beam 2, patience 2 | 5.4% | 3.1% | 5.2% | 94.7% | 30/30 / 30/30 | 1 / 1 | 38.37 s |
| Same, beam 3, patience 1 | 4.9% | 4.1% | 4.7% | 93.6% | 29/30 / 30/30 | 0 / 1 | 35.33 s |
| Same, temperature fixed at zero | 4.7% | 3.1% | 4.7% | 94.7% | 30/30 / 30/30 | 0 / 1 | 41.07 s |
| Full FP16, beam 5, patience 2, threads 2 | 4.9% | 3.1% | 4.9% | 94.7% | 30/30 / 30/30 | 0 / 1 | 223.42 s |

Total compute is the sum of timed chunk transcription, excluding model loading
and the separate warmup. These fast file replays do **not** measure Stop-to-text
latency: multiple chunks queue immediately. The sequential case order is fixed,
so the small timing differences are not an alternating or randomized comparison.
The large FP16 slowdown is nevertheless directly observed across all workflows.

## What the controls resolve

The application uses two CPU threads, while the previous comparison harness
used eight. The two-thread baseline reproduces the current 4.7% overall and
3.1% medical error, and all cleaned transcripts match the eight-thread control.
Total compute differs by about 0.2%; this run provides no meaningful reason to
change the app's CPU thread setting.

All seven configurations selected temperature zero for every emitted segment,
including warmup. The remaining errors in these recordings therefore do not
come from higher-temperature fallback. Forcing zero does not test recovery
behavior on recordings that actually need fallback, and is not adopted.

Beam 3/patience 2 saved 8.1% of aggregate compute but lost one scored medical
word in a letter. Its eight messages and ten results have identical cleaned
text to the baseline. The result-snippet compute saving was just 0.071 s total
over ten clips; message saving was 0.734 s over eight clips. One exam's cleaned
text also changed without changing that workflow's aggregate error count.
Beam 2 added a numeric-token mismatch in a letter; reduced patience lost a
formatting check. Aggregate equality on one category is insufficient evidence
of clinical equivalence on new speech.

Full float16 was 5.47 times slower in total compute and slightly worse in overall
error. It is a different comparison from the earlier **int8_float16 versus
int8_float32** tests. The current runtime keeps INT8-quantized weights and uses
float32 for nonquantized computation; the full-float16 control requests float16
throughout. Effective device and compute type were verified on the loaded
CTranslate2 object. See [CTranslate2's precision documentation](https://opennmt.net/CTranslate2/quantization.html).

## GPU, bounds and provenance

GTX 1660 Ti, 6,144 MiB, driver 610.60. Whole-card memory across the matrix peaked
at **5,088 MiB** (including desktop/model loading), with a **72 C** peak sampled
temperature. Utilization samples reached 99%. The matrix used the existing
OS-held `results_medasr/.overnight.lock`, one owned child at a time, a 300-second
child limit and 30-minute total limit. All seven children exited successfully;
the runner is complete and releases its lock. No package or model was added.

The runtime adapter requires an existing local CTranslate2 snapshot, enforces
offline loading and English transcription, and refuses device/precision
fallback. Model files, corpus audio and common source fingerprints were checked,
plus the runtime/chunk adapter hashes. Every checkpoint includes the actual
settings and lazy segment confidence/temperature diagnostics. A source/model
change or incomplete trace cannot publish completed success. Transcripts,
diagnostics and telemetry remain ignored under
`results_medasr/runtime_20261004`; its aggregate is `scores.json`.

This adapter changes no production source or decoding default. Its full unit
suite passed: **418 tests in 29.47 seconds**, using headless Qt.

## Paced short-workflow follow-up

Eighteen message/result recordings were replayed at microphone pace in beam-5,
beam-3, beam-5 order, with patience 2, two threads, INT8/f32 and 30-second cuts.
Every run passed source/model/adapter/corpus validation. Overall WER was 3.6%
in this short-only subset for all three runs (message 4.0%, result 2.3%).

| Workflow | Clips per run | Beam 5 A median / p95 | Beam 3 median / p95 | Beam 5 B median / p95 |
|---|---:|---|---|---|
| Messages | 8 | 1.485 / 1.687 s | 1.426 / 1.644 s | 1.506 / 1.710 s |
| Results | 10 | 1.038 / 1.076 s | 1.022 / 1.146 s | 1.046 / 1.152 s |
| Combined | 18 | 1.073 / 1.687 s | 1.138 / 1.644 s | 1.127 / 1.710 s |

Compared with the average of the two beam-5 controls, beam 3 saved about
**28 milliseconds in mean finishing delay** across the eighteen clips. The
message mean improved by about 72 ms, while the result mean was about 7 ms
slower. The mixed-category median does not improve. This small observation
does not justify introducing another automatic mode with a medical-word loss
on longer material. Keep beam 5 for the single recording workflow.

These are warm Stop-to-formatted-text observations, excluding GUI polling and
clipboard operations, with the same GPU sampler in all runs. They are one
reused corpus in A/B/A order rather than independent samples or a randomized
clinical trial. Small samples make p95 particularly weak; it is the maximum for
each category. Artifacts are under `runtime_20261004/paced`; all three children
and their supervising runner finished successfully.

## Switching controls

Beam and precision are independent. A beam setting can change between
recordings on one loaded model. Precision is selected at model loading; changing
it requires reload or separately resident models, with measured loading and
memory costs. Full FP16 offers no demonstrated benefit here, and a large beam
must remain available for complex medical speech. Automatic switching is not
implemented on the basis of these reused calibration examples.

The broad optimization goal remains active. New personal recordings, actual
whispered-speech sensitivity, interactive latency and a held-out accuracy check
remain necessary; see [optimization status](../OPTIMIZATION_STATUS.md).

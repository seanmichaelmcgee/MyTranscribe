# MedASR trial status — 2026-10-03

This is the archived overnight comparison. See the [4 October optimization and
current product report](2026-10-04-asr-optimization.md) for nine decoder trials,
matched Whisper controls, 30-second chunk accuracy/timing and compact input feedback.

## Outcome

**Keep Whisper as the working engine.** MedASR float32 is exceptionally fast on
this machine, and recognizes some exam vocabulary better, but it makes more
overall/common-word errors and still mishandles some numbered letters. The
formatter-enabled real comparison is 11.2% overall WER for MedASR versus 6.2% for
Whisper; medical error is 4.1% versus 5.1%. That limited medical-score advantage
does not justify adopting the new engine for the user's main workflows.

Both planned matrices are complete: 16 initial tasks finished at 22:13 Halifax
and 14 native-format tasks at 22:53 on 3 October. The final native-format artifacts
were independently rechecked against current source/corpus/configuration hashes,
official model integrity and saved output hashes. No trial GPU worker remains active.
The night finished early because the planned comparisons were done.

The same 30 local fictional practice recordings reproduce the committed Whisper scorecard exactly. Production Whisper settings and GUI behavior have not changed.

The official pinned model downloaded and verified at approximately 21:35 Halifax
after local OAuth/model access succeeded. The first runner began at 21:40:37 with
a six-hour deadline. The native-format runner began at 22:21:11 with a shortened
budget ending at 03:39:11; neither needed its deadline. Scheduled monitoring and
the five-hour recovery checkpoint were both paused at 23:09 Halifax after the
completed report was pushed. No further unattended trial is scheduled.

## Reproduced Whisper baseline

large-v3, CUDA int8_float32, beam 5, patience 2; topic prompts, committed correction rules and final voice commands. Names ignored by the existing scorer. Audio and reference fingerprints are stored only in ignored local results.

| Category | WER % | Medical error % | Common error % | Rare unmatched /100 | Terms % | Newline/quote counts | Mean Stop→formatted text | Max |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| message | 4.0 | 0.0 | 3.8 | 0.0 | 100.0 | 8/8 | 1.53 s | 1.80 s |
| result | 2.3 | 7.1 | 0.0 | 0.0 | 95.0 | 10/10 | 1.01 s | 1.11 s |
| exam | 8.5 | 6.7 | 9.8 | 1.1 | 87.5 | 9/9 | 1.27 s | 1.54 s |
| letter | 7.2 | 5.1 | 7.4 | 0.4 | 93.3 | 3/3 | 3.01 s | 3.55 s |
| ALL | 6.2 | 5.1 | 6.1 | 0.4 | 93.6 | 30/30 | 1.43 s | 3.55 s |

Latency is one warm 1× paced replay per clip: 8 messages, 10 results, 9 exam fragments and 3 letters. It includes tail enqueue, worker draining and final formatting, but excludes GUI polling and clipboard transfer. The earlier “wait” column was fast file-processing time. These are preliminary timing observations; use repeated paired runs before choosing an engine.

Raw Whisper output scores 15.5% WER against spoken references, whereas cleaned output scores 6.2% against written references. These reference targets differ: spelled-out abbreviations and numeric forms can inflate raw WER. Do not interpret the difference as a pure spelling-corrector gain.

Newline/quote counts and numbered-item sequences are checks of structure, not proof that placement or clinical meaning is correct. Rare unmatched words are a frequency heuristic; medical/common error rates omit insertions. Review doses, units and negation separately.

## First matched MedASR pass

Official pinned weights, float32 CUDA, eager attention, greedy CTC; same app cuts
and cleanup as the frozen Whisper run. The raw model text contains native brace
markers that the current Whisper-oriented cleanup does not interpret correctly.
No marker conversion was introduced into this first comparison.

| Category | WER % | Medical error % | Common error % | Terms % | Newline/quote counts | Numbered sequence |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| message | 22.8 | 6.7 | 9.8 | 90.0 | 3/8 | 8/8 |
| result | 6.8 | 7.1 | 0.0 | 95.0 | 10/10 | 10/10 |
| exam | 13.8 | 0.0 | 18.0 | 100.0 | 9/9 | 9/9 |
| letter | 19.3 | 10.3 | 10.9 | 93.3 | 0/3 | 0/3 |
| ALL | 18.3 | 6.1 | 10.8 | 94.7 | 22/30 | 27/30 |

Raw WER against spoken references was 23.3%. Native marker counts were 12 newline,
three open-quote, three close-quote, three new-paragraph and nine period markers.
All 30 outputs were nonempty. Sum of chunk compute was 2.00 s for the corpus;
peak PyTorch allocated memory was 440.6 MiB. These are fast-replay observations,
not Stop-to-text latency or total system VRAM measurements.

The matrix will preserve this unadapted baseline before a separately labeled,
deterministic native-format experiment. The zero exam medical-error result is
encouraging but covers only nine clips. It does not offset the higher message and
letter error rates or establish clinical correctness.

## Completed precision and paced-delay checks

Float16 is **rejected on this runtime/GPU**: all 30 raw/cleaned outputs were empty
after whitespace trimming, producing 100% WER. It used 235.8 MiB peak allocated
memory but took 8.79 s summed compute versus float32's 440.6 MiB and 1.93 s in the
matched matrix pass. The process returned successfully, demonstrating why exit
status alone is insufficient to validate a model configuration. The numerical
failure was then reproduced on one waveform: its feature input was finite, but
all 109,568 logits were nonfinite. The exact failing kernel remains undiagnosed.
The adapter now rejects nonfinite logits explicitly. Continue with float32.

Three paced repeats per clip produced these warm Stop-to-final-formatted-text
measurements. Each engine ran separately on the same corpus; GUI polling and
clipboard transfer are excluded.

| Workflow | Replays per engine | Whisper median / p95 / max | MedASR float32 median / p95 / max |
| --- | ---: | --- | --- |
| message | 24 | 1.484 / 1.634 / 1.797 s | 0.207 / 0.289 / 0.303 s |
| result | 30 | 1.014 / 1.138 / 1.145 s | 0.160 / 0.192 / 0.192 s |
| exam | 27 | 1.244 / 1.547 / 1.595 s | 0.196 / 0.257 / 0.267 s |
| letter | 9 | 3.369 / 3.755 / 3.755 s | 0.298 / 0.359 / 0.359 s |
| ALL | 90 | 1.254 / 3.369 / 3.755 s | 0.191 / 0.303 / 0.359 s |

Paced cleaned WER was 5.8% for Whisper and 18.3% for MedASR, with medical WER
5.1% and 6.1% respectively. Repeats are correlated, and Whisper's prompt rotation,
decoding and capture timing can affect the repeated result; do not present the
small change from its 6.2% offline score as a software improvement. MedASR has
ample speed headroom for a deterministic formatting bridge, but speed does not
resolve the observed accuracy problems.

## Synthetic cross-checks and stability

| Dataset | Engine | WER % | Medical error % | Common error % | Terms % | Formatting counts |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| snippets (60) | Whisper | 1.7 | 5.1 | 0.6 | 94.7 | 59/60 |
| snippets (60) | MedASR unadapted | 11.9 | 0.0 | 5.6 | 98.9 | 44/60 |
| dictations (40) | Whisper | 4.6 | 11.4 | 1.8 | 83.5 | 40/40 |
| dictations (40) | MedASR unadapted | 12.4 | 17.3 | 6.8 | 71.9 | 40/40 |

These synthetic datasets are reported separately because texts/profile repeats
are correlated. They show the MedASR vocabulary benefit is not universal across
this test material. Five float32 real-corpus passes completed 150 decodes with
identical raw and cleaned output for each clip. Peak allocated memory ranged
425.4–440.6 MiB depending on clip length; no output instability was observed.

## Native-format experiment: first pass

The opt-in five-marker bridge is a small deterministic application policy, guided
by [Google's explanation of brace tokens](https://discuss.ai.google.dev/t/116107/4)
and the actual local marker inventory. It leaves unknown markers intact and
protects them from spelling guesses. The production Whisper app does not use it.

Its first fresh-source MedASR float32 replay scored **11.2% overall WER**, **4.1%
medical WER**, **10.6% common WER**, **94.7% term recall**, formatting counts
**29/30** and numbered sequences **28/30**. Letter formatting is still incomplete
(2/3 formatting counts, 1/3 numbered sequences); messages now pass 8/8 counts.
Raw recognition was byte-for-byte unchanged for all 30 clips versus the original
MedASR run, so this improvement comes from representation and downstream cleanup,
not a new acoustic model. Medical alignment scores can also change after formatting.

The new matrix's matched real scorecard confirms the same result against fresh
Whisper: 6.2% overall / 5.1% medical error for Whisper versus 11.2% / 4.1% for
native-format MedASR. Common-word error remains 6.1% versus 10.6%. Numeric-token
review flags occur on one Whisper clip and five MedASR clips; negation flags occur
on one and zero respectively. These are token-comparison alerts, including possible
formatting/representation differences, not verified clinical error counts. The
medical-score advantage alone does not justify changing the default engine.

A fresh paired native-format matrix completed at 22:53:07 Halifax, regenerating
Whisper under the same source fingerprint and repeating paced timing, synthetic
and stability checks. Original completed scorecards are archived and will not be
rescored with the modified pipeline.

## Final native-format paired measurements

| Workflow | Whisper WER / medical error | MedASR WER / medical error | Whisper formatting / numbering | MedASR formatting / numbering |
| --- | --- | --- | --- | --- |
| message (8) | 4.0 / 0.0% | 11.4 / 6.7% | 8/8 / 8/8 | 8/8 / 8/8 |
| result (10) | 2.3 / 7.1% | 6.8 / 7.1% | 10/10 / 10/10 | 10/10 / 10/10 |
| exam (9) | 8.5 / 6.7% | 13.8 / 0.0% | 9/9 / 9/9 | 9/9 / 9/9 |
| letter (3) | 7.2 / 5.1% | 10.8 / 5.1% | 3/3 / 3/3 | 2/3 / 1/3 |
| ALL (30) | 6.2 / 5.1% | 11.2 / 4.1% | 30/30 / 30/30 | 29/30 / 28/30 |

The numbered-sequence total includes clips without numbered items. The letter
row makes the remaining deficit clearer: only one of three numbered letters
matches the expected sequence. Count-based formatting also cannot prove placement.

Final warm paced Stop-to-text measurements include the native bridge, shared
cleanup and final commands, with three repeats per real clip:

| Workflow | Replays per engine | Whisper median / p95 / max | Native MedASR median / p95 / max |
| --- | ---: | --- | --- |
| message | 24 | 1.483 / 1.631 / 1.689 s | 0.220 / 0.286 / 0.305 s |
| result | 30 | 1.009 / 1.145 / 1.189 s | 0.154 / 0.184 / 0.192 s |
| exam | 27 | 1.243 / 1.546 / 1.551 s | 0.196 / 0.261 / 0.271 s |
| letter | 9 | 3.343 / 3.742 / 3.742 s | 0.231 / 0.348 / 0.348 s |
| ALL | 90 | 1.246 / 3.343 / 3.742 s | 0.190 / 0.295 / 0.348 s |

GUI polling/clipboard transfer are excluded. Median differences favor MedASR by
roughly 0.85–1.26 s for short workflows and 3.11 s for letters. Offline WER remains
the primary 30-clip paired score; paced repeats produce Whisper WER 5.8% and
MedASR 11.2%, and are not additional independent examples.

The adapted synthetic snippets score 4.7% overall / 0.0% medical WER for MedASR
versus 1.7% / 5.1% for Whisper. All 60 MedASR snippets pass formatting and numbering
counts; Whisper passes 59/60 formatting and 60/60 numbering. Native conversion
does not improve the separate 40-dictation set: MedASR remains 12.4% overall /
17.3% medical error versus Whisper 4.6% / 11.4%. Numeric-token review flags are
4 versus 1 on snippets and 23 versus 7 on dictations, again requiring local review
rather than being interpreted as confirmed clinical mistakes.

Five adapted real-corpus passes produced identical raw and cleaned output per
clip; within-clip peak allocated memory spread across repeats was 0.0 MiB. The
maximum sampled GPU temperature in this matrix was 76 °C, below the 85 °C stop
threshold; no thermal stop occurred. Initial model load/warmup were 6.60/1.72 s
for Whisper and 6.39/0.31 s for MedASR, separate from warm dictation delay.

## Runtime and isolation

- NVIDIA GTX 1660 Ti, 6144 MiB VRAM, driver 610.60; PyTorch confirms CUDA availability.
- Separate ignored `venvmedasr`; PyTorch 2.13.0+cu126, Transformers 5.18.0. Complete dependency constraints are in `requirements-medasr.lock.txt`.
- Original install hit Windows MAX_PATH in deeply nested PyTorch license files; extended-path installation resolved it without registry/security changes. Dependency check reports no conflicts.
- `scripts/smoke_medasr.py` passed preprocessing → generation → decoding on CUDA using a tiny **random-weight** LASR model. This tests the API, not trained MedASR performance.
- Downloader accepts only official `google/medasr` revision `ae1e4845b4b07479735d93e1e591e566435b7104`, allowlisted tokenizer/config files and safetensors weights; it checks upstream weight SHA256 and saves local hashes. Inference is offline, with remote code disabled.
- No practice recordings/transcripts were uploaded; models, environments and detailed results remain gitignored.

## Verification and limitations

- Full unit suite including overnight orchestration, native-format policy and numerical guard: **282 passed in 28.06 s** with `QT_QPA_PLATFORM=offscreen`.
- Native Windows Qt run: 224 passed, 1 clipboard roundtrip failure. A standalone plain Qt clipboard write also fails; Win32 `OpenClipboard` returns access denied (error 5) in the agent process. The same clipboard test passes with the headless Qt platform. No clipboard implementation or assertion was weakened; actual native clipboard integration remains unverified in this execution context.
- Frozen Whisper baseline and paced replay both completed and were accepted by the matching scorer.
- Corpus/source changes, incomplete runs, duplicate clips/repeats and missing transcripts are rejected by the new scorer.

## Next useful experiments

See [the local trial guide](../MEDASR_TRIAL.md) and [completed overnight plan](2026-10-03-medasr-overnight-plan.md). Prioritize new real examples of the user's paragraph-style referrals, quick result messages, and numbered items. Review the flagged numbers, terms and negation locally, then keep a held-out set when changing prompts or formatting. The existing synthetic repetitions and three letters cannot establish broad clinical accuracy.

If continuing MedASR, its more promising next research question is decoder/context
support and reliable spoken-command interpretation, rather than a faster GPU.
Google's external 6-gram decoding and sliding-window example are separate
configurations requiring a documented dependency/provenance review and new paired
evaluation. No external decoder, LLM reviewer, new model, fine-tuning or cloud run
was introduced tonight. An LLM reviewer would need its own tests for changed or
invented clinical content and added latency before being considered.

The current machine has ample MedASR inference headroom. A 4070 Ti Super or rented
H100/RTX Pro 6000 is not justified by these measured bottlenecks; more GPU memory
will not by itself fix the observed recognition and formatting errors. Keep the
experimental runtime isolated until a future comparison supports adoption.

The primary replay uses the current app’s 20 s non-overlapping pause cuts. Google’s 20 s/2 s-overlap sliding example is a separate candidate configuration. Greedy CTC can make substitutions and insertions; it does not guarantee absence of hallucination.

Primary references: [Google MedASR model card](https://huggingface.co/google/medasr), [LASR documentation](https://huggingface.co/docs/transformers/model_doc/lasr), [Google terms](https://developers.google.com/health-ai-developer-foundations/terms), [official CUDA wheel instructions](https://pytorch.org/get-started/previous-versions/).

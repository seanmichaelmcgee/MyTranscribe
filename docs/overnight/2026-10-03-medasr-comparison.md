# MedASR trial status — 2026-10-03

## Outcome

The isolated MedASR dependencies and CUDA audio/CTC API work on this machine. Local OAuth is authenticated as `smichaelmcgee`; model access now works. The official pinned snapshot was downloaded and checksum-verified at approximately 21:35 Halifax. Its first float32 GPU pass completed all 30 recordings and was accepted by the matched scorer. The initial 16-task matrix completed at 22:13 Halifax. MedASR is much faster, but accuracy is currently worse overall than Whisper. A separate native-format configuration is being evaluated; this is not an adoption recommendation.

The same 30 local fictional practice recordings reproduce the committed Whisper scorecard exactly. Production Whisper settings and GUI behavior have not changed.

The tested overnight matrix started at 21:40:37 Halifax in a hidden local process,
with a six-hour deadline at 03:40:37. The first scheduled check confirmed completed
accuracy, precision, paired paced-latency, synthetic and stability runs. Scheduled
chat checks run every 30 minutes, with a separate recovery
checkpoint around 02:40 after five hours. Native-format findings will be appended
when they exist.

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

A fresh paired native-format matrix launched at 22:21:11 Halifax, regenerating
Whisper under the same source fingerprint and repeating paced timing, synthetic
and stability checks. Its 5.3-hour deadline is 03:39:11. Findings are pending.
Original completed scorecards are archived and will not be rescored with the
modified pipeline. Keep Whisper as the working application for now.

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

## Resume the trained-model comparison

See [the local trial guide](../MEDASR_TRIAL.md) and [the six-hour overnight plan](2026-10-03-medasr-overnight-plan.md). Ensure the signed-in account has accepted MedASR access conditions; repeating login will not fix denied model access. Then download and verify the pinned snapshot, replay the same 30 clips with MedASR, and score the paired runs. Follow with 3 warm paced repeats and separately labeled synthetic cross-checks. Inspect raw output for native punctuation/format tokens before adding any conversion; do not guess replacements that could alter dictated medical content.

The primary replay uses the current app’s 20 s non-overlapping pause cuts. Google’s 20 s/2 s-overlap sliding example is a separate candidate configuration. Greedy CTC can make substitutions and insertions; it does not guarantee absence of hallucination.

Primary references: [Google MedASR model card](https://huggingface.co/google/medasr), [LASR documentation](https://huggingface.co/docs/transformers/model_doc/lasr), [Google terms](https://developers.google.com/health-ai-developer-foundations/terms), [official CUDA wheel instructions](https://pytorch.org/get-started/previous-versions/).

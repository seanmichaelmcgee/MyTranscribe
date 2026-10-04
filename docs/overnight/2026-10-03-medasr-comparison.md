# MedASR trial status — 2026-10-03

## Outcome

The isolated MedASR dependencies and CUDA audio/CTC API work on this machine. The trained model has **not been downloaded or evaluated**: browser sign-in does not authorize the local downloader, and the first CLI OAuth device code expired without authorization. No MedASR accuracy, latency, VRAM comparison or adoption recommendation is available yet.

The same 30 local fictional practice recordings reproduce the committed Whisper scorecard exactly. Production Whisper settings and GUI behavior have not changed.

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

## Runtime and isolation

- NVIDIA GTX 1660 Ti, 6144 MiB VRAM, driver 610.60; PyTorch confirms CUDA availability.
- Separate ignored `venvmedasr`; PyTorch 2.13.0+cu126, Transformers 5.18.0. Complete dependency constraints are in `requirements-medasr.lock.txt`.
- Original install hit Windows MAX_PATH in deeply nested PyTorch license files; extended-path installation resolved it without registry/security changes. Dependency check reports no conflicts.
- `scripts/smoke_medasr.py` passed preprocessing → generation → decoding on CUDA using a tiny **random-weight** LASR model. This tests the API, not trained MedASR performance.
- Downloader accepts only official `google/medasr` revision `ae1e4845b4b07479735d93e1e591e566435b7104`, allowlisted tokenizer/config files and safetensors weights; it checks upstream weight SHA256 and saves local hashes. Inference is offline, with remote code disabled.
- No practice recordings/transcripts were uploaded; models, environments and detailed results remain gitignored.

## Verification and limitations

- Full unit suite: **225 passed in 26.53 s** with `QT_QPA_PLATFORM=offscreen`.
- Native Windows Qt run: 224 passed, 1 clipboard roundtrip failure. A standalone plain Qt clipboard write also fails; Win32 `OpenClipboard` returns access denied (error 5) in the agent process. The same clipboard test passes with the headless Qt platform. No clipboard implementation or assertion was weakened; actual native clipboard integration remains unverified in this execution context.
- Frozen Whisper baseline and paced replay both completed and were accepted by the matching scorer.
- Corpus/source changes, incomplete runs, duplicate clips/repeats and missing transcripts are rejected by the new scorer.

## Resume the trained-model comparison

See [the local trial guide](../MEDASR_TRIAL.md). Finish CLI OAuth authorization and ensure the signed-in account has accepted MedASR access conditions. Then download and verify the pinned snapshot, replay the same 30 clips with MedASR, and score the paired runs. Follow with 3 warm paced repeats and separately labeled synthetic cross-checks. Inspect raw output for native punctuation/format tokens before adding any conversion; do not guess replacements that could alter dictated medical content.

The primary replay uses the current app’s 20 s non-overlapping pause cuts. Google’s 20 s/2 s-overlap sliding example is a separate candidate configuration. Greedy CTC can make substitutions and insertions; it does not guarantee absence of hallucination.

Primary references: [Google MedASR model card](https://huggingface.co/google/medasr), [LASR documentation](https://huggingface.co/docs/transformers/model_doc/lasr), [Google terms](https://developers.google.com/health-ai-developer-foundations/terms), [official CUDA wheel instructions](https://pytorch.org/get-started/previous-versions/).

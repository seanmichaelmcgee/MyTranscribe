# Vocabulary / accuracy round 2026-10-03 (evening) — paused here

Runtime: faster-whisper large-v3, **CUDA** on the GTX 1660 Ti, int8_float32.

## Real-recording results (user's headset, 30 clips, names ignored)
| | start of round | now |
|---|---|---|
| medical-word error | 8.2 % | **5.1 %** |
| invented words / 100 | 0.9 | **0.4** (both flagged in the UI) |
| formatting right | 29/30 | **30/30** |
| overall error | 7.3 % | 6.2 % |
| Stop→text, 10 s snippet | ~1.4 s | ~1.6 s |

Synthetic check (100 files): 3.5 % WER, 8.3 % medical, formatting 99/100 — no regression.

## What changed (all committed)
- Beam 5 + patience 2 (greedy doubled medical errors on real speech).
- No generic term list in the prompt until a topic is detected (lists = distractors).
- Corrector: near-phonetic band (amlodiphene→amlodipine, arithmatous→erythematous),
  plural-aware; regression 79/79 fixes, 0 wrong. Merged words never auto-corrected.
- text_fixes: "H-E-E-N-T"→HEENT; personal `corrections.txt` ("heard => correct").
- +122 exam/skin/symptom/lab terms; non-words flagged ("Copied — check: …").
- Ruled out: fp16 (same accuracy, 7× slower), VAD off, timestamp mode, word-confidence flags.
- Tools: `ablate_decoding.py`, `probe_word_confidence.py`, name-insensitive medical/invented scoring.

## Next candidates
1. **Google MedASR trial** (below). 2. NVIDIA Parakeet-TDT-0.6B-v2 via sherpa-onnx (true hotword
boosting, transducer = can't free-write words). 3. More real recordings (paragraph letters).

## MedASR trial plan (brief)

> MedASR update: the trial tooling and reproduced Whisper baseline are recorded in
> [2026-10-03-medasr-comparison.md](2026-10-03-medasr-comparison.md).
> The predictions below about CTC preventing inventions and sub-0.5-second latency
> are unverified expectations, not guarantees or results. Use the new report for current status.

- **What:** Google `medasr`, 105M-param CTC model trained on ~5,000 h of physician dictation;
  reported 6.0 % vs 12.5 % (large-v3) on Eye Gaze dictation. CTC cannot invent fluent words;
  weak on general speech (≈18 % LibriSpeech) → staff messages may suffer.
- **Licence first:** Health AI Developer Foundations terms (regulatory-authorization clause,
  Google may restrict use) — read before any clinical use; a trial on our practice recordings is fine.
- **Isolation:** separate venv (`venvmedasr`), never mixed into the app venv; transformers ≥ 5 +
  PyTorch CPU/CUDA; download weights once from `google/medasr` (safetensors only — refuse pickle),
  record SHA256; then `HF_HUB_OFFLINE=1`.
- **Harness:** add a `MedAsrEngine.transcribe(audio, prompt) -> text` (prompt ignored), map its
  `{period}/{new line}/{paragraph}` tokens to our voice-command formatter, run our post-processing
  chain, and score with `ablate_decoding.py`-style metrics on `results_1060/real_headset` and the
  synthetic sets. Optional: pyctcdecode + hotwords from our lexicon.
- **Decide on:** medical-word error, invented words (expect ~0), common-word error on messages,
  formatting, Stop→text latency (likely < 0.5 s), VRAM. Adopt only if it beats large-v3 on medical
  words without losing messages; a hybrid (MedASR for exam/results snippets) is possible.
- **Effort:** ~half a day.

## Instructions for the agent running the MedASR comparison (same folder, same PC)

**Current-build scorecard to beat** (exact app config: large-v3, CUDA, int8_float32, beam 5,
patience 2, topic-only term list, corrector + text_fixes, voice commands; names ignored):

| category | WER | medical | everyday | invented/100 | terms | format | wait |
|---|---|---|---|---|---|---|---|
| exam | 8.5 | 6.7 | 9.8 | 1.1 | 87.5 | 9/9 | 1.06 s |
| letter | 7.2 | 5.1 | 7.4 | 0.4 | 93.3 | 3/3 | – |
| message | 4.0 | 0.0 | 3.8 | 0.0 | 100 | 8/8 | 1.26 s |
| result | 2.3 | 7.1 | 0.0 | 0.0 | 95.0 | 10/10 | 0.82 s |
| **ALL** | **6.2** | **5.1** | **6.1** | **0.4** | **93.6** | **30/30** | **1.03 s** |

Synthetic cross-check (testdict + snippets, 100 files): ALL 3.5 % WER, 8.3 % medical, format 99/100.

**Data (local only, gitignored — user's practice voice reading fictional text; never commit or upload):**
- Real: `results_1060/real_headset/manifest.json` (30 clips: 8 message, 10 result, 9 exam, 3 letter).
- Synthetic: `results_1060/testdict/manifest.json`, `results_1060/snippets/manifest.json`.

**Steps**
1. Reproduce the baseline first (confirms the environment matches the table):
   `venv1060\Scripts\python.exe scripts\ablate_decoding.py --manifest results_1060\real_headset\manifest.json --settings base+patience=2.0 --show-invented --json results_1060\real_headset\scorecard_current.json`
2. Set up MedASR in its **own** venv (`venvmedasr`); do not install anything into `venv1060`.
   Read the Health AI Developer Foundations terms; download `google/medasr` once (safetensors only),
   record SHA256 in the report, then run with `HF_HUB_OFFLINE=1`.
3. Score MedASR with the **same scorer**: `src/eval_metrics.py` → `breakdown()` (name-insensitive WER,
   medical-word error via `load_medical_words` + each entry's `terms`, everyday-word error, invented
   words) plus `term_hits` and the format check (line-break/quote counts equal to the reference).
   Easiest: a small script in `venvmedasr` that writes `{audio: hypothesis}` JSON, then score those
   hypotheses with a scoring-only mode added to `scripts/ablate_decoding.py` (or a twin script) so
   chunking-independent metrics are computed identically. Apply our post-processing to MedASR
   output too (`vocab.build_text_pipeline(...)[1]` and `voice_commands.apply`), after mapping its
   `{period}` / `{comma}` / `{new line}` / `{paragraph}` tokens to punctuation / "New line." text.
   Report both "raw" and "with our post-processing".
4. Report per category (table above), invented words listed, Stop→text latency per snippet,
   VRAM/CPU use, and any clips where either system is clearly worse (paste hypotheses — fictional).
5. Commit scripts + a report to `docs/overnight/<date>-medasr-comparison.md` on branch
   `claude/festive-einstein-lb2tk9`. Never commit audio, `results_*` folders or model files.

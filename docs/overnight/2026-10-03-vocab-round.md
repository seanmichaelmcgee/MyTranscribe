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

# Personal prompt budget fix — 4 October 2026

## Failure and resulting behavior

A personal style file could pass the loader's 1,200-character limit while
exceeding the prompt builder's 215-token budget. A dense medical example measured
490 tokens with the actual large-v3 tokenizer. Previously, the builder returned
that oversized style when there was no room for vocabulary. The engine then
subtracted all 490 prompt tokens from the decoder window and reduced its output
allowance to the 24-token minimum, potentially truncating a long dictation.

The builder now measures the complete prompt, preserves recent dictated context
first, and fits the style's whole-word suffix into the remaining budget. Each
vocabulary addition also checks the complete assembled prompt. Already-fitting
text stays intact, and the fitting helper does not log prompt text. The dense
example now measures 209 tokens without context and 215 with the tested context.

The engine separately counts only the prompt suffix that faster-whisper actually
retains. In the installed 1.2.1 implementation, a 448-token decoder window retains
at most 223 preceding prompt tokens, plus the preceding-text marker and four
transcription setup tokens. This leaves a 220-token output allowance for the
direct dense-prompt example, while the existing duration-based output guard
still applies to short audio. See the pinned
[faster-whisper implementation](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py).

This bounds personal examples; it does not make a vocabulary list an instruction
following system or establish better recognition from a large list. Important
terms belong near the end of a short, representative style example.

## Verification and limits

- **425 tests passed in 29.36 seconds**, including the prompt/context budget,
  whole-word retention and decoder-window regression checks, with headless Qt.
- A fresh replay of all 30 saved fictional voice recordings used the changed
  source fingerprints, the same local model snapshot and the same corpus. Every
  raw transcript, cleaned transcript and raw chunk matched the pre-fix baseline.
  Overall WER remains **4.7%**, medical WER **3.1%**, common WER **4.7%**, format
  and numbering **30/30** each, with zero numeric-token flags and one negation
  flag. These are reused calibration samples, not independent clinical evidence.
- An isolated integration check kept audio, dense prompt and beam settings
  identical and changed only the output allowance. The prior 24-token allowance
  returned 5 words; the corrected 220-token allowance returned 49 words. Both
  outputs reached their respective limits. This demonstrates output starvation;
  it does **not** establish transcription accuracy or complete coverage of the
  letter under that deliberately overfull prompt.

No production model, beam, precision, recording control, input gain or spelling
correction policy changed. New personal paragraph and whispered-speech recordings
remain necessary to evaluate those workflows.

## Provenance and execution

Pre-fix runtime measurements are preserved with their original source hashes in
`results_medasr/runtime_20261004`, documented in the
[runtime report](2026-10-04-whisper-runtime.md) and committed as `e961060`.
The fresh changed-source replay and dense-prompt check are ignored under
`results_medasr/prompt_budget_20261004`; `scores.json` records the full-corpus
baseline and `dense_prompt.json` the cap-only demonstration. Old artifacts were
not relabeled as results from the changed code.

The full-corpus replay validated common source, corpus, model and adapter
fingerprints. The cap-only check records source/corpus/audio fingerprints and
uses that same existing local snapshot; it is an isolated diagnostic, not a
scored matrix entry. Recognition was offline and received no reference text.
The shared OS-held GPU lock serialized the jobs, with a 300-second child limit,
a 30-minute supervisor limit and an 85 C thermal boundary. Both jobs exited
successfully and released the lock. The final check peaked at 5,804 MiB whole-card
memory, including other desktop use, and 55 C sampled GPU temperature.

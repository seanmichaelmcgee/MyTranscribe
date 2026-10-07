# Worker 01: Whisper short-input prompts and contextual vocabulary

Write only `results_1060/accuracy_program_20261004/workers/01-whisper-prompt/`.
Read WORKER_COMMON.md. Inspect fw_engine.py, vocab.py, prompt_loader.py,
medical_prompt.txt, chunked_transcriber.py and the two phone control matrices.

Explain the approximately-three-second style-example copying failure using
actual runtime/prompt/token traces and official Whisper/faster-whisper/CT2
documentation. Investigate prompt versus hotword mechanisms, abbreviations,
broad vocabulary hints, duration/context policies, prompt echo rejection,
confidence limitations and whether chunk/context handling can reduce these errors.
Do not repeat already-rejected settings as new discoveries. Identify why removing
the prompt helped one file but harmed the prior corpus. No desired test sentences,
sample-specific numbers or external reference text may become inference hints.

Deliver at most three ranked, distinct, concrete candidates; preferably an
inspectable CPU prototype or patch sketch in your own folder and a compact
matched trial matrix. Specify how to prevent prompt-derived values and how to
avoid erasing true spoken lab values. Preserve clinical values and non-word
correction safeguards. State the evidence needed for the <=10-second workflow.
Run no model inference or source edit. Checkpoint citations, confirmed behavior
and hypotheses separately.

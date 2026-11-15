# Pause-aware dictation: thinking pauses, spoken commands and the last words (2026-11-15)

Status: **candidate, off by default.** Options → "Pause-aware dictation", or `MYTRANSCRIBE_PAUSE_AWARE=1`. With it off the pipeline is the classic one, unchanged. This note is the sanitized summary; recordings, transcripts and per-recording results stay in the ignored `results_1060/reliability/` tree.

## What was wrong (classic pipeline, measured)

1. **A cut in a thinking pause splits the sentence.** Audio is cut at the quietest moment near 30 s. A thinking pause is the quietest moment, so the cut often lands mid-clause; Whisper then closes the chunk with a full stop and opens the next with a capital.
2. **Spoken commands are sometimes left out altogether.** When Whisper writes "New paragraph." the conversion works; the failures are commands that never reach the text, as if they were filler. It happens per decoding window and is worse when pauses are present.
3. **Stop can cut the last word.** If the key is released 0.15 s before the last word finishes, the word is lost or replaced by an invented one.
4. A few quiet words after a long pause could be skipped as "silence" (whole-chunk average level), and one failed decode replaced a chunk's text with an error marker.

## What the candidate does

| Change | Where |
|---|---|
| The unfinished last sentence of a chunk is not committed; its audio (≤ 6 s) is decoded again with the next chunk. Capture target becomes 24 s so every decode still fits the model's 30 s window. A chunk ending on a spoken command is kept whole. | `chunked_transcriber.py`, `pause_flow.split_for_carry` |
| Holes in the word timings that contain sound get one quick (greedy) second listen; a command heard there is put back. Nothing but a command is ever inserted, and not if one is already next to the hole or the model is unsure of it. | `pause_flow.command_in_hole`, `ChunkedTranscriber._rescue_commands` |
| "new paragraph" written without punctuation is accepted; "new line" too unless its neighbours make it a noun phrase ("a new line of therapy"). | `voice_commands.apply(lenient=True)` |
| Capture continues 0.3 s after Stop (post-roll). | `ChunkedTranscriber.stop_recording` |
| A failed decode is retried once; a chunk is silent only if no 0.3 s stretch reaches the level threshold. | `chunked_transcriber.py` |
| Word timings without the "Thank you." tail: faster-whisper re-decodes the leftover tenths of a second in word-timestamp mode; that pass is skipped. | `fw_engine.transcribe_words` |

## How it was measured

`scripts/dictation_reliability.py` runs each recording through the app pipeline as captured and under five derived conditions (see its docstring): thinking pauses of 1.5 s and 4 s spliced mid-clause with the recording's own room tone, 2 s pauses around every command, a 3 s pause before the last two words, and Stop arriving 0.15 s before the last word ends. Corpus: 47 fictional headset recordings by the owner (short messages, results, exams, letters of 20-100 s), split by session into 24 development and 23 held-out recordings. The candidate was tuned on the development split only; the held-out split was run once, at the end. Model: faster-whisper large-v3, int8_float16, RTX 4070 Ti SUPER. No external service.

WER is against the read-aloud script (number and unit spelling differences count as errors, so absolute values are pessimistic; compare columns). "Breaks" are sentence ends that appear at a spliced pause and are not in the same pipeline's output for the original recording. "Commands" are formatting marks matched in order against the reference.

### Held-out split (23 recordings, run once)

| Condition | WER % base → cand | Breaks | Commands found | Format ok | Last words ok |
|---|---|---|---|---|---|
| as recorded | 4.52 → 4.45 | - | 54/56 → 56/56 | 11/12 → 12/12 | 21/23 → 21/23 |
| 1.5 s pauses (54 sites) | 5.81 → 5.39 | 6 → 2 | 48/52 → 52/52 | 8/10 → 10/10 | 9/10 → 9/10 |
| 4 s pauses (54 sites) | 5.81 → 6.06 | 2 → 1 | 52/52 → 48/52 | 10/10 → 9/10 | 9/10 → 9/10 |
| pauses around commands | 5.56 → 4.74 | 1 → 2 | 49/56 (+2 extra) → 56/56 | 7/12 → 12/12 | 11/12 → 11/12 |
| pause before last words | 4.56 → 4.48 | 1 → 1 | 54/56 → 56/56 | 11/12 → 12/12 | 18/20 → 18/20 |
| Stop 0.15 s early | 6.48 → 4.82 | - | 53/56 → 56/56 | 10/12 → 12/12 | 2/23 → 18/23 |

Compute for the as-recorded set: 35.3 s → 40.2 s (+14 %).

### Development split (24 recordings, used for tuning)

| Condition | WER % base → cand | Breaks | Commands found | Last words ok |
|---|---|---|---|---|
| as recorded | 12.17 → 11.49 | - | 50/54 → 54/54 spoken | 20/24 → 20/24 |
| 1.5 s pauses (80 sites) | 14.40 → 13.03 | 7 → 4 | 39/51 → 45/51 | 8/10 → 8/10 |
| 4 s pauses (80 sites) | 13.66 → 13.37 | 18 → 8 | 38/51 → 45/51 | 8/10 → 8/10 |
| pauses around commands | 13.49 → 12.49 | 8 → 2 | 49/58 → 51/58 | 9/13 → 9/13 |
| pause before last words | 12.86 → 11.53 | 2 → 1 | 50/58 → 52/58 | 15/20 → 16/20 |
| Stop 0.15 s early | 14.12 → 11.43 | 2 → 1 | 47/58 → 52/58 | 5/24 → 19/24 |

Compute for the as-recorded set: 46.9 s → 46.6 s. (One development recording omits part of its script, including four commands; the counts out of 58 and 51 include those four.)

Variants tried on top of the candidate and not adopted (development split): VAD padding 150 ms and 100 ms, and VAD off. None improved breaks without costing accuracy or commands; VAD off was worse on every pause measure.

## Limitations

- **Known regression:** with 4 s pauses one held-out letter lost four list commands that the classic pipeline kept (48/52 vs 52/52), and WER in that condition rose 5.81 → 6.06. Commands inside a numbered list ("new line, 2 period") are the weak spot.
- Pauses are spliced into read-aloud recordings. Real hesitation (fillers, restarts, trailing intonation) is not in the corpus and is untested.
- Pauses inside a chunk still cause some sentence breaks and an occasional dropped word next to the pause (8 of 80 sites at 4 s on the development split). Only the breaks caused by the chunk cut are addressed.
- Under spliced pauses the candidate writes more comma-joined sentences: sentence ends missing against the script rose (held-out, 1.5 s pauses: 5 → 11) while extra ones fell (16 → 10).
- When no sentence end with a usable pause lies in the last 6 s of a chunk, the chunk is committed whole, exactly as in the classic pipeline.
- Commands covered: new line, new paragraph, quotes, numbered items. Spoken "comma", "full stop", "colon" are not commands.
- Script-relative scoring; no listen-back adjudication and no clinical review of meaning. One speaker, one headset, one GPU. Not timed on the GTX 1060; live insert was not exercised with real audio.
- If a clipboard copy fails and a new recording is started, the uncopied text is still discarded (unchanged from the classic app).

## Reproduce

```powershell
.\venv1060\Scripts\python.exe scripts\dictation_reliability.py --corpus-root results_1060 --out results_1060\reliability\runs --split dev --profile baseline
.\venv1060\Scripts\python.exe scripts\dictation_reliability.py --corpus-root results_1060 --out results_1060\reliability\runs --split dev --profile candidate
```

Add `--model <folder>` to use a local model snapshot. CPU checks: `pytest -q tests/test_pause_flow.py tests/test_pause_aware_transcriber.py tests/test_voice_commands.py`.

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

## Dragon Medical One on the same audio (held-out split)

`scripts/dragon_replay.py` plays each held-out recording, and the same derived conditions, through a virtual audio cable (VB-CABLE) into Dragon Medical One 26.3 dictating into Notepad, one play per cell (98 cells, 62 minutes of audio). Dragon recognises in the cloud; only the owner's fictional recordings were sent. Scoring is the same code as above.

| Condition | WER % base / cand / Dragon | Commands found | Format ok | Last words ok |
|---|---|---|---|---|
| as recorded | 4.52 / 4.45 / 5.73 | 54/56, 56/56, 56/56 | 11/12, 12/12, 12/12 | 21/23, 21/23, 20/23 |
| 1.5 s pauses | 5.81 / 5.39 / 8.50 | 48/52, 52/52, 52/52 (+1 extra) | 8/10, 10/10, 9/10 | 9/10, 9/10, 9/10 |
| 4 s pauses | 5.81 / 6.06 / 8.50 | 52/52, 48/52, 52/52 (+1 extra) | 10/10, 9/10, 9/10 | 9/10, 9/10, 9/10 |
| pauses around commands | 5.56 / 4.74 / 7.11 | 49/56 (+2), 56/56, 52/56 (+3) | 7/12, 12/12, 7/12 | 11/12, 11/12, 11/12 |
| pause before last words | 4.56 / 4.48 / 6.69 | 54/56, 56/56, 56/56 | 11/12, 12/12, 12/12 | 18/20, 18/20, 15/20 |
| Stop 0.15 s early | 6.48 / 4.82 / 7.46 | 53/56, 56/56, 55/56 | 10/12, 12/12, 11/12 | 2/23, 18/23, 1/23 |

How to read it:

- Dragon writes sentence punctuation only when it is dictated. Against the script it leaves out about 130 sentence ends in every condition and adds none, so it never produces a spurious sentence break at a pause; that measure is not comparable and is left out of the table. WER ignores punctuation.
- Part of Dragon's WER rise under spliced pauses is an artefact of the splice: several pause sites fall inside a word ("recorded" split in two), which Dragon transcribes as two words and Whisper mostly repairs. The 1.5 s and 4 s results are nearly the same errors. Treat the pause rows as a stress test, not as how Dragon handles a natural pause.
- For Dragon, "Stop 0.15 s early" means the audio ends there and the microphone is switched off at once; the cable adds latency, so the timing is approximate.
- One play per cell, no repeat; a virtual cable, not a live microphone; script-relative scoring with no listen-back.

## Corti Med-Dictate (English, 24 notes, 66 minutes)

Run once on the finished candidate with `scripts/corti_benchmark.py`; nothing was tuned against it (the dataset licence allows benchmarking existing systems, not developing them). Dataset revision `2a840558`, file hash checked against the October acquisition receipt. Scored with the metric module frozen for the October benchmark ("conservative" view: case and punctuation marks ignored, number spellings kept). The spoken track is the text before command conversion against the verbatim reference; the formatted track is the final text against the publisher's formatted note. Dragon was not replayed: its figures are the saved October captures (23 notes; one capture failed then).

| 23 notes scored for all three | Existing | Candidate | Dragon (October) |
|---|---|---|---|
| Spoken track WER | 15.19% | 15.24% | 39.04% |
| Formatted track WER | 24.20% | 24.48% | 6.04% |

On all 24 notes: spoken 14.87% → 14.90%, formatted 23.97% → 24.23%; neither difference is distinguishable from zero (paired bootstrap over notes: −0.6 to +0.7 and −0.8 to +1.3 points). Compute 184 s → 213 s for 3,949 s of audio on the RTX 4070 Ti SUPER.

- These speakers dictate every punctuation mark. Of the 1,175 inserted words on the formatted track (existing pipeline), 1,027 are "period", "comma", "colon", "hyphen", "parenthesis" and similar, left in the text as words. Without those the formatted WER would be about 8.2% (8.4% candidate) against Dragon's 6.0%; that is arithmetic on the alignment, not a measured result.
- The spoken track mirrors it: Dragon turns the spoken marks into punctuation, so it scores badly against a verbatim reference, and the local pipelines lose about 590 reference words the same way where Whisper writes the mark instead of the word.
- The pause-aware changes do not address spoken punctuation marks, so no gain was expected here and none was found. No pause, command or early-Stop conditions were derived from this set.

## Spoken punctuation (added after the first Corti run)

Options → "Spoken punctuation", or `MYTRANSCRIBE_SPOKEN_PUNCTUATION=1`; off by default and independent of pause-aware dictation. `voice_commands.apply(punctuation=True)` turns "period" / "full stop", "comma", "colon", "semicolon", "question mark", "exclamation mark", "hyphen" and "open / close parenthesis" into the marks; the dictated mark replaces whatever the model wrote after the word. "period" and "colon" stay words when their neighbours make them a noun ("her last period", "a period of observation", "the sigmoid colon", "colon cancer"); that guard is a word list.

The owner's recordings contain almost no dictated marks, so the rules were written against a synthetic set: the corpus scripts read by the two Windows text-to-speech voices with every mark spoken (`scripts/spoken_punctuation_tts.py`), development split for writing the rules, held-out split run once. No Corti output was read while writing them; only the aggregate count of leftover mark words above was known.

| Check | Option off | Option on |
|---|---|---|
| Synthetic development (48 readings, 640 marks): mark words left in the text | 511 | 0 |
| Synthetic held-out (46 readings, 436 marks): mark words left in the text | 305 | 0 |
| Synthetic held-out: marks missing / added against the script | 23 / 28 | 8 / 9 |
| Synthetic held-out: WER | 14.62% | 2.95% |
| Real recordings (398 saved transcripts, all conditions): transcripts changed | - | 0 |
| Corti formatted track, 24 notes | 24.23% | 8.14% |
| Corti formatted track, the 23 notes with a Dragon capture (Dragon 6.04%) | 24.48% | 8.36% |

- Corti was run once with the option on. A spacing bug found afterwards on the owner's recordings was fixed and the saved Corti text re-converted without new recognition; one note's text changed and the totals did not. The Corti spoken track is unaffected (14.90%).
- The remaining gap to Dragon on Corti is not broken down here, deliberately: reading those errors to design the next change would be developing against the benchmark.
- A computer voice pauses and pronounces the marks more regularly than a person. The real evidence that a human's dictated marks are handled is the Corti result; the owner's own voice dictating marks is untested.
- False conversions are the risk: zero on the owner's recordings, which rarely contain "period" or "colon" as nouns, so that check is weak. The unit tests list the noun phrases that are protected.

## Limitations

- **Known regression:** with 4 s pauses one held-out letter lost four list commands that the classic pipeline kept (48/52 vs 52/52), and WER in that condition rose 5.81 → 6.06. Commands inside a numbered list ("new line, 2 period") are the weak spot.
- Pauses are spliced into read-aloud recordings. Real hesitation (fillers, restarts, trailing intonation) is not in the corpus and is untested.
- Pauses inside a chunk still cause some sentence breaks and an occasional dropped word next to the pause (8 of 80 sites at 4 s on the development split). Only the breaks caused by the chunk cut are addressed.
- Under spliced pauses the candidate writes more comma-joined sentences: sentence ends missing against the script rose (held-out, 1.5 s pauses: 5 → 11) while extra ones fell (16 → 10).
- When no sentence end with a usable pause lies in the last 6 s of a chunk, the chunk is committed whole, exactly as in the classic pipeline.
- Commands covered: new line, new paragraph, quotes, numbered items. Spoken "comma", "full stop", "colon" are converted only with the separate Spoken punctuation option (above).
- Script-relative scoring; no listen-back adjudication and no clinical review of meaning. One speaker, one headset, one GPU. Not timed on the GTX 1060; live insert was not exercised with real audio.
- If a clipboard copy fails and a new recording is started, the uncopied text is still discarded (unchanged from the classic app).

## Reproduce

```powershell
.\venv1060\Scripts\python.exe scripts\dictation_reliability.py --corpus-root results_1060 --out results_1060\reliability\runs --split dev --profile baseline
.\venv1060\Scripts\python.exe scripts\dictation_reliability.py --corpus-root results_1060 --out results_1060\reliability\runs --split dev --profile candidate
```

Add `--model <folder>` to use a local model snapshot. CPU checks: `pytest -q tests/test_pause_flow.py tests/test_pause_aware_transcriber.py tests/test_voice_commands.py`.

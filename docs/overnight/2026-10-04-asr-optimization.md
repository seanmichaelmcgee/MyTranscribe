# ASR optimization — 4 October 2026

## Current result

Resumed after the earlier overnight comparison stopped too soon. Two agents
implemented and reviewed independent formatting and Whisper-ablation work; the
parent implemented and ran the official-LM decoder experiment locally.

**Keep the working Whisper application.** Nine MedASR decoder configurations on
the same 30 fictional real-voice recordings lowered overall word error from
11.2% to 8.2%. Current Whisper reproduces 6.2%. The remaining gap is 11 word
errors out of 536 scored reference words. This is progress, not parity.

All experiments are isolated from production. No `src` files or model weights
were changed, no packages installed, and no audio/transcripts uploaded. Model
data and detailed results remain local and ignored by Git. The earlier overnight
automations remain paused; this is a new bounded, actively supervised iteration.

## Decoder calibration

Float32 CUDA acoustic logits were collected with the pinned official model. The
cache adapter reproduced all 30 original raw transcripts exactly. Decoder-only
iterations then used the same waveform/model/runtime/source-verified arrays,
loaded with pickle disabled. No reference, desired phrase or medical-term list
was given to recognition or decoding. Full scoring rejects stale fingerprints.
Artifacts collected before the agents finished source changes were excluded;
matched baselines and candidates were regenerated after source freeze.

All positive beams use experimental CTC prefix probability merging, at most 16
tokens per frame, threshold -8, and blank always retained. Alpha is the official
SentencePiece LM weight; beta is a per-piece insertion bonus. This small decoder
is not identical to Google's pyctcdecode implementation. The only external data
added were Google's checksum-pinned text six-gram probabilities, indexed locally
using Python/SQLite; no additional executable dependency was introduced.

| Configuration | Overall WER | Medical error | Common error | Format counts | Number sequence |
|---|---:|---:|---:|---|---|
| MedASR greedy + native formatter | 11.2% | 4.1% | 10.6% | 29/30 | 28/30 |
| Beam 8, no LM | 9.5% | 4.1% | 8.9% | 29/30 | 28/30 |
| Beam 8, alpha .5 / beta 1 | 10.1% | 3.1% | 10.6% | 30/30 | 29/30 |
| Beam 32, alpha .5 / beta 1 | 9.1% | 4.1% | 9.2% | 30/30 | 29/30 |
| Beam 8, alpha .35 / beta .75 | 9.5% | 3.1% | 10.1% | 30/30 | 29/30 |
| Beam 8, alpha .2 / beta .5 | 9.0% | 3.1% | 8.9% | 30/30 | 29/30 |
| **Beam 32, alpha .2 / beta .5** | **8.2%** | **3.1%** | **8.0%** | **30/30** | **29/30** |
| Beam 8, alpha .1 / beta .25 | 8.2% | 2.0% | 7.7% | 29/30 | 28/30 |
| Beam 32, alpha .1 / beta .25 | 8.2% | 3.1% | 7.5% | 29/30 | 28/30 |
| Current production Whisper | 6.2% | 5.1% | 6.1% | 30/30 | 30/30 |

The beam-32/.2/.5 candidate is the balanced formatting candidate, not an asserted
clinical optimum. Stronger LM weights worsened overall recognition. Beam 8/.1/.25
has fewer medical errors but leaves more malformed formatting. No default was
changed based on either calibration result.

The agent's local review found a clinically important tradeoff hidden by the
aggregate score: the balanced LM candidate loses an autoantibody identifier
retained by greedy MedASR and Whisper, while gaining another target term. The
weakest beam-8 LM candidate retains that identifier. Neither improved overall
WER nor unchanged negation flags establish that an LM candidate preserves every
clinical term. This is another reason to keep the experiment out of production.

| Workflow | Clips | Whisper WER / medical error | Balanced MedASR WER / medical error |
|---|---:|---|---|
| Messages | 8 | 4.0 / 0.0% | 8.7 / 0.0% |
| Results | 10 | 2.3 / 7.1% | 6.8 / 7.1% |
| Exam fragments | 9 | 8.5 / 6.7% | 8.5 / 0.0% |
| Letters | 3 | 7.2 / 5.1% | 8.0 / 5.1% |

Greedy MedASR had 60 errors; the balanced decoder has 44; Whisper has 33.
Medical denominators are only 98 words: balanced MedASR misses three, Whisper
five, and beam-8/.1/.25 two. These small differences do not establish broad
medical superiority. Medical/common rates omit insertions; overall WER includes
them. Raw/spoken and cleaned/written WER use different references.

Balanced MedASR has four numeric-token review flags and no negation-token flag,
versus Whisper's one and one. Greedy MedASR has five and zero. These signals
include representation differences and require review; absence of a flag does
not prove preservation of clinical meaning. Names are ignored by the existing
scoring policy. Number-sequence totals include clips without numbered lists.

## Formatting investigation

The opt-in bridge now handles mixed explicit native/spoken layout and numbered
commands. A constructed command matrix improves 23/35 to 35/35, with tests for
ordinary prose, clinical numbers/negation and unknown brace spans. All 370 saved
MedASR utterances remain unchanged by this formatter patch. It therefore repairs
a general command case without providing the measured corpus WER gain above.
That gain comes from decoder changes. Damaged commands are left for review,
including a missing brace or an unrecognized list-number word.

See [the agent's investigation](2026-10-04-medasr-format-investigation.md).

## Whisper regression investigation

The historical audit identified changes in topic prompts, spelling correction,
abbreviation/phrase fixes, output cap, chunks and decoding. Highlighting suspicious
words does not alter copied text. The controlled matrix tests current features
individually; it cannot by itself prove a historical regression. Capture-start
behavior and user-specific prompts/rules are outside this file-replay experiment.

The harness resets prompt rotation for each clip; the production-style trial
shares a builder across dictations. Both baselines reproduce 6.2% here. Source,
model, corpus, names policy, runtime and decoder defaults are frozen and verified.
No-reference waveform inputs are separated from scorer metadata. GPU variants
run sequentially with a 300-second worker timeout per variant.

| Current-feature control | Overall WER | Medical error | Common error | Format / number sequence |
|---|---:|---:|---:|---|
| Baseline: 20 s, beam 5 / patience 2 | 6.2% | 5.1% | 6.1% | 30/30 / 30/30 |
| No topic terms, same style/context tail | 6.3% | 5.1% | 6.3% | 30/30 / 30/30 |
| No rare-word corrector | 6.3% | 6.1% | 6.1% | 30/30 / 30/30 |
| No abbreviation/phrase fixes | 7.3% | 7.1% | 6.1% | 30/30 / 30/30 |
| No postprocessing | 7.5% | 8.2% | 6.1% | 30/30 / 30/30 |
| No prompt | 14.2% | 16.3% | 11.3% | 28/30 / 29/30 |
| Style only, no context/topic continuation | 11.9% | 12.2% | 11.5% | 29/30 / 29/30 |
| Greedy, patience 1 | 7.5% | 7.1% | 5.6% | 29/30 / 30/30 |
| Beam 5, patience 1 | 6.2% | 5.1% | 6.1% | 29/30 / 30/30 |
| **30 s chunks, other baseline settings retained** | **4.7%** | **3.1%** | **4.7%** | **30/30 / 30/30** |

**A chunk-size tradeoff was reproduced.** Restoring 30-second chunks reduces
errors from 33 to 25, entirely on two of the three letters; the other letter
has unchanged cleaned error count. Letter WER is 7.2% at 20 seconds and 4.0% at
30 seconds; letter medical errors are 5.1% and 0.0%. Other workflows are unchanged
because these clips do not reach either cut boundary. Numeric flags fall from
one to zero; the one exam negation flag remains. This supports a longer-letter
accuracy option pending Stop-to-text timing and new independent letters.

Current topic terms and cleanup do not show overall degradation here. The
corrector prevents one scored medical-word error, fixes prevent six overall
errors, and removing all postprocessing adds seven. Their removal did not
change raw output on this corpus. Removing prompts adds 43 cleaned errors.
Style-only and baseline first-chunk prompts are identical; its raw differences
occur only on the three multi-chunk letters. No claim is made that any of these
features can never harm another dictation.

See [the agent's historical audit and matched-run interpretation](2026-10-04-whisper-regression-audit.md).
## Measured finishing delay

One genuine 1x-paced replay per recording confirms the same 8.2% MedASR and
6.2% Whisper WER. MedASR used a fresh empty acoustic cache, so these are GPU
inference plus LM/formatting measurements, not cached-logit timing. Its local
cache writes are included. Both exclude GUI polling and clipboard transfer.
This was a supervised desktop run; some unit/scoring work occurred in the
background, so timings are observations rather than idle-machine guarantees.
Model load/warmup are excluded from the warm finishing delays.

| Workflow | Clips | Whisper 20 s median / p95 / max | MedASR LM median / p95 / max |
|---|---:|---|---|
| Message | 8 | 1.487 / 1.745 / 1.745 s | 0.339 / 0.386 / 0.386 s |
| Result | 10 | 1.037 / 1.230 / 1.230 s | 0.234 / 0.306 / 0.306 s |
| Exam | 9 | 1.264 / 1.564 / 1.564 s | 0.324 / 0.379 / 0.379 s |
| Letter | 3 | 3.426 / 3.732 / 3.732 s | 0.502 / 0.554 / 0.554 s |
| ALL | 30 | 1.284 / 3.426 / 3.732 s | 0.321 / 0.502 / 0.554 s |

The small letter sample's p95 is its maximum. MedASR has speed headroom even
with this Python/SQLite decoder, but the measured common-word, numeric and
clinical-identifier deficits still prevent a recommendation to replace Whisper.
The 30-second Whisper follow-up is recorded below when completed.

### Completed 30-second paced follow-up

The same 30 real recordings were replayed at microphone pace with an explicit,
fingerprinted 30-second override. Accuracy reproduced the isolated result:
4.7% overall WER, 3.1% medical WER, 30/30 formatting and numbering checks,
zero numeric review flags and one negation flag. All 27 short recordings had
identical cleaned transcripts at 20 and 30 seconds; two of three letters improved.

| Workflow | Clips | Whisper 20 s median / p95 / max | Whisper 30 s median / p95 / max |
|---|---:|---:|---:|
| Messages | 8 | 1.487 / 1.745 / 1.745 s | 1.526 / 1.674 / 1.674 s |
| Results | 10 | 1.037 / 1.230 / 1.230 s | 1.037 / 1.160 / 1.160 s |
| Exams | 9 | 1.264 / 1.564 / 1.564 s | 1.269 / 1.588 / 1.588 s |
| Letters | 3 | 3.426 / 3.732 / 3.732 s | 2.557 / 3.270 / 3.270 s |

This is Stop-to-formatted-text in the replay harness, excluding the GUI and
clipboard. Short recordings flush on Stop rather than waiting for 30 seconds.
The lower letter finishing delay in this particular run reflects how much
background work was completed before Stop; longer chunks do not guarantee
lower latency. Only three letters and one repeat were measured. Raw inference
compute on those letters increased with longer chunks, so do not extrapolate
these finishing-delay observations to every dictation length.

Artifacts: `whisper30_paced.json` and `paced_chunk_scores.json` in the ignored
`results_medasr/optimization_20261004` directory. These measurements precede
the subsequent production UI/default changes; their frozen source hashes remain
the provenance for this experiment.

## Synthetic cross-check

A separate matched replay of 60 synthetic snippets plus 40 synthetic dictations
completed on the same frozen source. Combined WER is 10.2% for greedy MedASR,
8.8% for the balanced LM decoder and 3.8% for Whisper. Medical error is 12.9%,
10.9% and 9.5%, respectively; common-word error is 6.4%, 5.0% and 1.5%.
The LM improvement therefore extends beyond the real-voice calibration clips,
but does not reach Whisper's overall accuracy on this material either.

These totals weight a mixed-length corpus and are not directly comparable to
the previous separately replayed synthetic scorecards: here Whisper's builder
is shared across the combined manifest order. Profile/text repetitions are
correlated, and these synthetic examples do not establish whispered-voice or
microphone performance. Detailed profile/workflow breakdowns remain local.

## Verification and interpretation

Full unit suite: **402 passed in 29.09 seconds**, using the headless Qt platform.
No GUI or clipboard integration change was made; the earlier native clipboard
restriction remains outside these accuracy experiments. Prefix beam tests compare
merged probabilities against exhaustive small CTC path enumeration, exercise
blank-separated repetitions, and verify ARPA backoff/base-10 conversion.

These 30 recordings are a reused **calibration set**, not a held-out test. Only
three letters are represented. Synthetic profile/text repeats are correlated.
The next independent evaluation needs new paragraph-style referrals and quick
result messages, with medication, number and negation review. Repeated tuning on
the current examples must not be described as evidence of general clinical
accuracy. GPU capacity alone does not resolve the remaining recognition errors.

Reproduction: [decoder experiment guide](../MEDASR_DECODER_EXPERIMENT.md),
[Whisper audit/harness guide](2026-10-04-whisper-regression-audit.md).
Primary decoder reference: [Google's official quickstart](https://github.com/Google-Health/medasr/blob/main/notebooks/quick_start_with_hugging_face.ipynb).

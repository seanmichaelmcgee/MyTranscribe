# Overnight MedASR comparison: 3–4 October 2026

## Completion

The initial matrix completed at 22:13 and the native-format matrix at 22:53:07
Halifax on 3 October. All 14 final artifacts passed an independent provenance,
integrity, coverage and completion audit during the 23:04 check. No GPU job is
active. The final recommendation and measurements are in the comparison report.
Both scheduled monitors were confirmed paused at 23:09 Halifax; no recovery run
is needed because all scoped comparisons have completed. Preserve the local
results for review. No further unattended trial is scheduled.

## Objective and boundaries

Establish whether the official Google MedASR model improves this clinician's
medical vocabulary while keeping short dictation responsive. The shipped Whisper
GUI and its defaults remain the working product. This night evaluates an isolated
runtime using existing fictional recordings, without microphone recording,
clipboard access, patient data, cloud inference or new training data.

Use the existing branch `claude/festive-einstein-lb2tk9` and PR #4. Commit only code,
tests, documentation and aggregate measurements. Audio, transcripts, model weights,
credentials, environments and detailed results remain local and gitignored.

## Access decision while the user is available

Local Hugging Face OAuth is authenticated as `smichaelmcgee`. Model access was
initially denied, but a new download succeeded at approximately 21:35 Halifax;
the pinned snapshot is now checksum-verified locally. This clears the human access
gate. Browser login alone does not grant model access. Do not repeat device-code
authentication unless the credential itself has expired or changed. Do not
automate accepting contact-sharing or model-access conditions.

## Six-hour execution budget

The runner has a six-hour wall-clock deadline, per-job timeouts, exclusive locking,
atomic progress files and sequential GPU jobs. It completes early if the matrix is
finished. A scheduled check in this same chat inspects progress every 30 minutes;
the local runner continues independently during a Codex usage-window pause.
The monitoring cutoff is 04 October 2026 at 03:45 Halifax (06:45 UTC). Any runner
started later gets only the time remaining to that cutoff, not another six hours.

The actual matrix launched at 21:40:37 Halifax with a runner deadline of 03:40:37.
Progress is in ignored `results_medasr/overnight_20261003/status.json`; the outer
launch PID is recorded in `results_medasr/overnight_launch.json` (initial PID 4668).
The main chat monitor is `mytranscribe-overnight-medasr`. A separate five-hour
recovery checkpoint, `mytranscribe-five-hour-recovery`, is scheduled around 02:40
Halifax to recover work after a Codex usage-window interruption. Inspect both
automation states before creating more checks; pause them after all work is done.

The initial 16-task matrix completed at 22:13 with no thermal stop. Its float16
process completed, but scored 100% WER because of nonfinite logits; reject that
configuration. The source has since changed for the explicit numerical guard and
opt-in five-marker formatting bridge. Do not resume the archived initial run.
The next active output directory is `results_medasr/overnight_native_20261003`,
with launch information in `results_medasr/overnight_native_launch.json`. Use
`--native-format --hours 5.3` when inspecting/resuming this new 14-task matrix;
its original deadline must still be preserved. Read its status before launching
anything else. When it completes, update the paired native-format report and
recommend the working engine based on accuracy and speed, then pause the monitors
if all scoped work is complete. This run excludes the failed float16 configuration.
The native-format matrix launched at 22:21:11 Halifax (initial outer PID 5996),
with deadline 03:39:11, inside both the original night budget and monitor cutoff.

All measurements use the pinned official safetensors snapshot and verify its
integrity before GPU work. Source and corpus fingerprints prevent stale runs from
being resumed or scored as current. A timed-out child may be terminated with its
own descendants; never terminate unrelated Python processes. Stop new GPU work
after sustained temperature above 85 °C. Do not alter drivers, antivirus, registry,
power policies or the current application to force a test through.

## Ordered matrix

| Phase | Recordings and settings | Question |
| --- | --- | --- |
| Paired accuracy | All 30 real headset clips; frozen Whisper and MedASR float32; identical app pause cuts and text cleanup | Does medical vocabulary improve, and which errors remain? |
| Precision | Same 30 clips; MedASR float16 versus its float32 run | Is a speed or memory saving accompanied by changed output? |
| Finishing delay | Both engines, all real clips, paced playback, three repeats | Median, p95 and worst Stop-to-formatted-text by workflow; include backlog, startup and warmup separately |
| Synthetic cross-check | Both engines on the 60 snippets, then the 40 dictations; separate scorecards | Are findings consistent across speech style and microphone profiles? |
| Stability | Five repeated real-corpus passes of MedASR float32 | Does output vary, memory grow, or inference fail? |

After this matrix completes, evaluate a separately labeled deterministic
native-format bridge. The initial real output contains exactly `{newline}`,
`{open quote}`, `{close quote}`, `{new paragraph}` and `{period}`. Verify their
meaning against the official model material and actual local output. Convert only
known exact markers; preserve unknown markers for review. Keep the unadapted run,
raw text and marker frequencies. Do not alter the scoring references or medical
words to make the result look better. If changing fingerprinted adapter/pipeline
source, start a new paired real run and repeat paced timing after its tests pass;
never edit it while the primary matrix is running. Report both configurations.

The user also has a 4070 Ti Super with 16 GB VRAM and could consider a rented
H100/RTX Pro 6000. Tonight uses this machine and the current official snapshot.
Initial MedASR allocation is only 440.6 MiB, so no evidence currently justifies
moving this trial or spending on a rental. Remote transfers/rental arrangements
require a concrete follow-up decision if a future experiment demonstrates need.

The synthetic sets reuse texts, and repeats are correlated. They do not turn the
30 real recordings or three letters into a larger independent clinical dataset.

## Decisions driven by the results

The existing matched real Whisper baseline is 6.2% overall WER, 5.1% medical WER,
6.1% common WER and 93.6% tracked-term recall. New paired runs take precedence over
historical figures. Show raw versus spoken references and cleaned versus written
references separately, from the same decode; do not attribute their whole
difference to the corrector because the reference representations differ.

For short snippets, another two seconds of finishing delay is unacceptable to the
user. Compare absolute Stop-to-text as well as the paired difference, with p95 and
worst cases rather than averages alone. Longer 30–60 second letters can tolerate
roughly two seconds more, subject to improved accuracy. Existing Whisper means
were 1.53 s for messages, 1.01 s for results, 1.27 s for exams and 3.01 s for letters.
Replay timing excludes GUI polling and clipboard transfer; label that limitation.

Check medical/common error rates, missing medical terms, rare unmatched words,
newlines, quotes and numbered-item order. Review numeric and negation differences
locally before suggesting adoption. Count checks do not establish correct layout
or clinical meaning. Names remain exempt under the existing scoring rules.

If greedy MedASR has poor vocabulary or command recognition, assess those failures
before adding components. Its CTC decoder has no Whisper-style vocabulary prompt.
Sliding windows, external language-model decoding and hotword biasing require
separately labeled experiments and a documented implementation/dependency review.
Do not quietly introduce an LLM reviewer or train on the scoring references.
If float16 fails or regresses, retain float32 and report the failure. Do not hide
CPU fallback under GPU performance figures. Change only one experiment variable
at a time and regenerate a paired baseline after pipeline/source changes.

## Morning deliverable

Update `2026-10-03-medasr-comparison.md` with actual model access and run status,
category accuracy, finishing-delay distributions, memory/stability observations,
formatting limitations, and a clear recommendation or remaining blocker. Keep
error transcripts in ignored result files. Run the appropriate tests before
committing code, then push only the existing branch. Disable the scheduled monitor
after completion or the cutoff. Keep this chat available for the user's review.

The computer and Codex app must remain running for scheduled local checks.

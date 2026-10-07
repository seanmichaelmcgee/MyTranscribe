# Whisper accuracy regression audit — 2026-10-04

## Finding and evidence boundary

The history contains changes capable of changing recognition or final text. This
audit does **not** establish that added features degraded accuracy. No model/GPU
inference was performed. Commit messages and previous findings describe earlier
experiments; their numbers are historical claims, not new matched ablation results.
The new harness isolates current feature effects on a frozen corpus. Establishing
a historical regression would additionally require an older source/model pipeline
and current source evaluated on identical audio/reference/scoring inputs.

Read: `CLAUDE.md`, `LOCAL_SESSION_HANDOFF.md`, `scripts/trial_asr.py`,
`scripts/asr_trial_common.py`, `scripts/score_asr_trial.py`, `scripts/ablate_decoding.py`,
and the current engine, chunker, vocabulary, correction, prompt-loader, GUI and
evaluation modules. Initial audit HEAD: `f3f05c3`. Other agents are changing
experiment source; plan creation must wait until the parent's full source freeze.

## Historical changes

| Commit | Confirmed source change | Interpretation |
|---|---|---|
| `019d6f0` | Separate medical app, faster-whisper engine, pause-cut background chunks, medical style prompt | Different pipeline from the earlier application; not an accuracy-controlled migration experiment |
| `9d39219` | Topic vocabulary/rotation, non-word spelling corrector, shortened style prompt | Several simultaneous changes; cannot attribute their combined result to one feature |
| `6300e27` | Beam 5 → greedy; introduced bounded output token cap | Accuracy/speed tradeoff was motivated by earlier synthetic findings; cap remains today |
| `e1150c7` | Chunk target 30 → 20 seconds | Changes acoustic boundaries and prompt frequency; short clips below either boundary cannot test this effect |
| `1983481` | Ready microphone retained | Capture/start behavior changes; file replay cannot evaluate clipped first words or microphone readiness |
| `2c4c42f` | Near-phonetic correction acceptance and plural-aware rival matching | Broader correction acceptance; finite regression examples do not establish correctness on a new corpus |
| `fc30d85` | Abbreviation joining plus bundled/user phrase corrections after corrector | Changes text independently of model decoding, and may change subsequent prompts |
| `8a6ee35` | Removed generic vocabulary sampling before any topic is detected | Current first-chunk prompt normally has style only; topic lists activate from prior recognized text |
| `03e7de1` | Greedy → beam 5 / patience 2 | Reverted greedy after reported real-voice differences; not an active greedy default today |
| `8ee33bd` | Suspicious-word checking/highlighting | Does not change copied text; its reporting is not recognition proof |
| `7c3f577` | GTX 16xx compute preference and best-accuracy model option | Hardware/model choices are additional confounders; hold model/device/precision fixed |

The handoff's original 30-second/turbo/int8_float16 expectations are older than
current source. Current source uses 20-second chunks, beam 5/patience 2; GTX 16xx
selection favors int8_float32, with large-v3 available through best accuracy.

## Current flow and state across dictations

PCM is 16 kHz mono int16, read in 1024-frame blocks. At about 20 seconds the chunker
cuts at the quietest 30 ms frame in the last five seconds, carrying the remainder.
Chunks below RMS 80 are skipped. One worker decodes chunks in order. The engine
uses English, condition_on_previous_text=False, VAD with 700 ms silence and 300 ms
padding, no timestamps, and installed faster-whisper temperature fallback defaults.
The production output cap depends on audio duration, prompt tokens, and the
448-token decoder window. Changing a prompt can therefore also change output room.

`PromptBuilder` uses bundled style, detected topics (up to three), vocabulary rotation,
and a 160-character tail of **already postprocessed** text. Topic detection scans
800 characters. With no detected or configured topic it returns style plus tail,
without vocabulary. The stated budget is 215 tokens, but the fixed style/tail branch
does not enforce a final hard trim; a pathological fixed prompt could exceed it.
Phantom filtering precedes spelling correction, then text_fixes. Voice commands
are applied to the final joined text in the trial. Consequently, disabling correction
or fixes may change later model output through context, beyond merely changing final
spelling. Raw paired scores help reveal this feedback.

The production `MYTRANSCRIBE_AUTOCORRECT=off` disables **both** corrector and fixes.
`MYTRANSCRIBE_VOCAB=off` selects a static-prompt fallback with a **200-character**
tail. These environment flags are not independent matched controls. The new
`no-topics` keeps the same PromptBuilder/160-character tail but empties its lexicon;
it isolates topic terms without the static fallback's tail-length change.

**Shared rotation matters across separate dictations.** `gui_med._load_engine`
builds the pipeline once and attaches it to a reused transcriber. Starting a new
recording clears transcriptions, chunk statistics and capture buffers; it does
not clear `PromptBuilder._rotation`. Topics are recalculated from the new recording's
own context, so prior transcript text does not carry across dictations, but term
selection offsets can persist once topics activate. The original `trial_asr.py`
likewise builds one builder before its clip/repeat loops. The older ablation script
explicitly clears rotation per clip. Shared rotation can create order-dependent
prompts on multi-chunk dictations; it is a plausible mechanism to measure, not
evidence that the GUI is wrong or accuracy regressed.

The harness's `baseline` deliberately creates a fresh pipeline for each clip/repeat.
It is a controlled current-feature baseline and **may differ from frozen6.2 and
the original trial's shared-builder baseline**. Parent will run the original
current trial as an additional comparison. Optional `shared-topics` reuses one
builder/postprocessor across the ordered corpus/repeats, while per-recording
transcript context still resets. Comparing that variant to `baseline` isolates
pipeline state reuse within this harness. It is not part of the default seven.
Corrector counts are cumulative in shared mode; its matching rules are otherwise
stateless. Corpus order is frozen in the plan. No shuffled-order claim is made.

## Harness controls and execution contract

New files: `scripts/whisper_accuracy_ablation.py` and
`tests/test_whisper_accuracy_ablation.py`. No production source or existing scripts
were changed by this audit.

| Variant | Change from reset-per-clip baseline |
|---|---|
| `baseline` | Topic prompting, corrector, fixes, beam 5/patience 2, 20-second chunks |
| `no-topics` | Disable topic/core terms; preserve style and identical tail construction |
| `no-corrector` | Disable only rare non-word corrector; fixes remain enabled |
| `no-fixes` | Disable only abbreviation/phrase text_fixes; corrector remains enabled |
| `no-prompt` | Explicit empty prompt on every chunk; no style, topics, or context tail |
| `greedy` | Beam 1/patience 1; faster-whisper temperature fallback retained |
| `beam-patience1` | Beam 5/patience 1 only |
| `no-post` (optional) | Disable corrector and fixes together |
| `bare` (optional) | Empty prompt plus no corrector/fixes; phantom filtering and voice commands retained |
| `style-only` (optional) | Fixed style example only, without tail/topic terms |
| `chunk30` (optional) | 30-second chunks only |
| `shared-topics` (optional) | Reuse pipeline across dictations/repeats in frozen order |

The default seven are baseline, no-topics, no-corrector, no-fixes, no-prompt, greedy,
and beam-patience1. They change one feature each (greedy changes the inseparable
beam/patience pair). These are opt-in file replays, without mic, GUI or clipboard.
Only existing local CTranslate2 model directories are accepted, with
local_files_only=True and offline environment flags; nothing downloads or installs.
Device/precision fallback is refused. CPU threads default to eight to match the
primary trial. Keep the parent-selected large-v3 snapshot and int8_float32 fixed.

All manifests, audio, run outputs and comparisons must be under an existing
gitignored `results_*` directory. Use `results_medasr` or `results_overnight`;
an arbitrary new results directory is not automatically ignored by this repository.
Model weights may use the existing external cache. Recognition receives only
audio paths/identity/duration. References, target terms and names are used only in
fingerprints and scoring, never supplied to model/prompt/correction inputs. Hidden
user vocabulary, topic overrides, prompt overrides and personal corrections are
excluded; bundled files are frozen. This cannot evaluate undocumented personal
configuration effects in the user's GUI session.

`plan` performs no inference. It freezes corpus metadata/audio, all common source
hashes, a separate mandatory experiment fingerprint (harness, eval_metrics, scorer,
trial), model file hashes, package versions, Python/platform, variants and bounds.
Parent's additions to `asr_trial_common.source_hashes` remain effective. Source or
dependency changes require a new plan and a complete fresh matrix. Do not replace
old fingerprints with current hashes. Full model hashing has CPU/disk cost.

`run` requires --execute and runs one variant in a child process, with a hard wall
timeout including model loading, corpus replay, and final fingerprint validation.
Defaults: <=100 clips, <=1800 aggregate audio seconds including repeats, one repeat,
1800 wall seconds per variant. Explicit ceilings: 500 clips, 7200 audio seconds,
three repeats, 7200 wall seconds. Inputs exceeding bounds are rejected rather than
silently sampled. Every utterance is checkpointed with completed=False; timeout or
failure leaves it unscorable. Hook failures swallowed by production are tracked and
refused. No warmup is performed; first-clip timing includes cold decoding effects.
These offline compute/processing timings are not real Stop-to-text latency, and
missing latency/VRAM measurements are null, not zero. CUDA inference is outside
this audit and is performed sequentially by the parent after source freeze.

## Parent launch examples after full source freeze

PowerShell; choose the actual existing corpus manifests (repeat --manifest for more
than one). Do not rename synthetic/practice data as a clinical real-world corpus.
References must faithfully match the audio. Supply `spoken` separately from written
`reference` when voice commands/layout differ; the existing scorer falls back to
written reference if spoken is absent, which limits raw-score interpretation.

```powershell
$pythonExe = '.\venv1060\Scripts\python.exe'
$modelSnapshot = 'C:\Users\smich\.cache\huggingface\hub\models--Systran--faster-whisper-large-v3\snapshots\edaa852ec7e145841d8ffdb056a99866b5f0a478'
$corpusManifest = 'results_1060\real_headset\manifest.json' # replace with selected existing corpus
$ablationDir = 'results_medasr\whisper_ablation_20261004'
& $pythonExe scripts\whisper_accuracy_ablation.py plan --manifest $corpusManifest --model-path $modelSnapshot --device cuda --compute int8_float32 --cpu-threads 8 --out "$ablationDir\plan.json"
if ($LASTEXITCODE -ne 0) { throw 'Plan rejected' }

$variants = @('baseline','no-topics','no-corrector','no-fixes','no-prompt','greedy','beam-patience1')
foreach ($variant in $variants) {
    & $pythonExe scripts\whisper_accuracy_ablation.py run --plan "$ablationDir\plan.json" --variant $variant --out "$ablationDir\$variant.json" --execute
    if ($LASTEXITCODE -ne 0) { throw "Incomplete variant: $variant" }
}
$scoreArgs = @('scripts\whisper_accuracy_ablation.py','compare','--plan',"$ablationDir\plan.json",'--out',"$ablationDir\comparison.json")
foreach ($variant in $variants) { $scoreArgs += @('--run',"$ablationDir\$variant.json") }
& $pythonExe @scoreArgs
if ($LASTEXITCODE -ne 0) { throw 'Comparison rejected' }
```

For optional controls specify the complete list with --variants at plan time, then
run/compare every selected variant. `run` refuses existing output paths; use a fresh
folder after a failure or changed source. The private --worker option is solely for
the harness's child process; parent launches always use the public commands above.

## Scoring and interpretation

This uses its own `whisper-accuracy-ablation-v1` schema/validator and then calls the
existing scorer's `score_run`; do not pass its JSON to the schema-1 trial validator
or patch source_sha256 to make old results pass. Both common and separate experiment
fingerprints are checked against current files before comparison. Each planned
variant needs exactly every clip/repeat, correct audio identity, completed=True,
the same plan/model/runtime fingerprint, valid chunk traces, actual decoder kwargs,
and finite consistent timing. Partial matrices, duplicate variants, missing or
duplicate utterances, changed decoder defaults, altered records and fallback runs
are rejected. Additional original-trial results remain separately validated by
their own scorer; their numbers are not merged as if they had identical state.

Historical name-insensitive scoring is preserved through `entry_names` and
`eval_metrics.breakdown`: supplied names plus established scenario fallback names
and titles are excluded as before. Raw text is scored against spoken reference;
cleaned text against written reference. The existing scorer supplies aggregate
WER/medical/common error counts and rates, rare unmatched words, term recall,
formatting/numbering counts and numeric/negation review signals by category.
Clinical correctness cannot be concluded from those review signals alone.

Paired deltas align clip_id/repeat and sum exact edit counts and reference-word
denominators, without averaging rounded per-clip WER. Candidate minus baseline:
negative error delta favors the candidate. Report improved/worsened/unchanged clips
and inspect categories/long dictations as well as total errors. Repeats are not
independent recordings; no significance claim is attached. A no-topics difference
on single-chunk clips should normally be absent because neither receives topics
without prior context. Long clips are required to test topic/context/shared-state
effects. The all-disabled and chunk-length variants test different questions from
individual feature controls.

## Validation performed

CPU-only tests cover provenance tampering/staleness, changed audio/reference/names,
package/model fingerprints, ignored-path requirements, opt-in and worker timeout,
independent prompt/corrector/fix controls, production decode kwargs/patience/cap,
real chunker replay with a fake engine and corrected-context feedback, swallowed
postprocessor failures, paired name-insensitive arithmetic, spoken-versus-written
reference selection, and rejection of incomplete comparison matrices. Frequency
scoring tests use an injected deterministic function; this is not corpus accuracy
validation. No model runtime or GPU is imported by those tests.

The venv1060 launcher currently points to an unavailable Python 3.11 executable in
this session. Tests can run without installs using the bundled Python 3.12, bundled
NumPy, and the existing venv's pure-Python pytest packages appended to sys.path.
This does not establish that the existing native inference environment is runnable;
parent must use its working inference environment and keep its versions frozen.

Final test result is recorded in the task's ready signal. No commits, pushes,
installs, corpus model runs or production edits were made by this audit.

## Follow-up: parent's completed matched matrix — 2026-10-04

The parent subsequently ran ten variants sequentially on the real-headset practice
corpus and produced
`results_medasr/optimization_20261004/whisper_comparison.json`. These are actual
matched measurements, unlike the historical claims above. This follow-up only
reads local results and edits this document; it performs no inference. The harness
source remains frozen at SHA-256
`0c6410d5da0cef28f7f1ea9aeff43897c6bfc2d8604a667e42a82cbdcd24b4fc`.

The comparison's plan fingerprint is
`94ec5a27c994d77a95120bc3a6edfc53c6f73417138605fa2ccb16d4b5861fe5`;
corpus fingerprint is
`e44d42875abc928e1a2f3fdc07872381fd3ca20d36283e3635f2d0eef4f58d24`.
Current common/experiment source fingerprints and corpus identity match the saved
plan. All ten completed run records passed the harness's run validator against
that plan/corpus, and their record fingerprints match the comparison's run links.
This read-only follow-up did not rerun model inference or independently rehash the
external model weights. Frozen run metadata records large-v3 from the specified
existing snapshot, CUDA/int8_float32, eight CPU threads, one repeat, and the same
dependency versions. Neither shared-topics nor bare was part of this ten-run matrix.

### Aggregate observed results

Cleaned/written-reference scores, with the historical names/titles exclusion
unchanged: 30 recordings, 536 reference words, 98 medical words and 426 common
words. Rates are percentages; exact error counts retain the unrounded evidence.

| Variant | Errors | WER | Medical WER | Common WER | Format counts correct |
|---|---:|---:|---:|---:|---:|
| baseline, 20 s | 33 | 6.2 | 5.1 | 6.1 | 30/30 |
| no-topics | 34 | 6.3 | 5.1 | 6.3 | 30/30 |
| no-corrector | 34 | 6.3 | 6.1 | 6.1 | 30/30 |
| no-fixes | 39 | 7.3 | 7.1 | 6.1 | 30/30 |
| no-post | 40 | 7.5 | 8.2 | 6.1 | 30/30 |
| no-prompt | 76 | 14.2 | 16.3 | 11.3 | 28/30 |
| style-only | 64 | 11.9 | 12.2 | 11.5 | 29/30 |
| greedy | 40 | 7.5 | 7.1 | 5.6 | 29/30 |
| beam-patience1 | 33 | 6.2 | 5.1 | 6.1 | 29/30 |
| chunk30 | 25 | 4.7 | 3.1 | 4.7 | 30/30 |

On this corpus, removing prompt/context, correction or fixes did not improve total
cleaned accuracy. Some changes are small: no-topics and no-corrector each add only
one error. Greedy reduces common-word errors from 26 to 24 but increases total
errors and medical errors. Beam patience 1 ties baseline aggregate word error
counts, but loses one formatting-count success on `01_message__real.wav`; matching
WER therefore does not establish equivalent formatting behavior.

The chunk30 difference is eight fewer cleaned errors out of the same 536 reference
words: an exact -1.4925 percentage-point WER delta. Medical errors fall 5 → 3,
common errors 26 → 20, rare unmatched words per 100 reference words 0.4 → 0.2,
and term hits 88/94 → 89/94. Formatting and numbering remain 30/30. Numeric review
mismatches fall 1 → 0; negation mismatches remain 1. These token-based flags remain
review signals, not proof that every number or clinical statement is correct.

### Per-letter concentration and correlation

All eight fewer cleaned errors occur in two of three letters. The third letter
and all 27 non-letter recordings have unchanged cleaned edit counts.

| Recording | Audio seconds | Reference words | Errors, 20 s → 30 s | Delta | Decoder calls, 20 s → 30 s |
|---|---:|---:|---:|---:|---:|
| `27_letter__real.wav` | 36.608 | 88 | 6 → 5 | -1 | 2 → 2 |
| `28_letter__real.wav` | 37.888 | 99 | 10 → 3 | -7 | 2 → 2 |
| `29_letter__real.wav` | 24.832 | 62 | 2 → 2 | 0 | 2 → 1 |

For letters alone, errors fall 18/249 → 10/249 (WER 7.2% → 4.0%); medical
errors fall 2/39 → 0/39 and common errors 15/202 → 9/202. The numeric flag removed
is on letter 27. Letter 28 supplies seven of the eight fewer cleaned errors, so
the aggregate result is dominated by one recording. Letters 27 and 28 still have
two model calls in either condition: chunk30 changes cut placement and the
audio/context available in each call, rather than simply removing a call there.
This experiment does not separate those mechanisms.

Raw/spoken-reference results also favor chunk30 in aggregate: 98/634 → 87/634
errors across the corpus (-11 errors), with all changes in the three letters.
Raw letter deltas are -5, -7 and +1 respectively; the third letter therefore
worsens slightly in raw recognition even though its cleaned edit count ties.
Raw letter WER falls 14.4% → 10.6%. This supports an effect before final output
clean-up, while preserving the distinction between raw and written-reference
metrics and possible cross-chunk postprocessing feedback.

There are only **three letter recordings**, one repeat, and effectively two
improving letter outcomes. Words/errors within a letter share audio conditions,
chunk boundaries and generated context; they are correlated and must not be
treated as hundreds of independent trials. The 27 unchanged short recordings
do not add equivalent evidence about long-dictation chunking. No statistical
significance or universal 30-second advantage is established. Selecting the best
of ten conditions on this corpus also calls for confirmation on held-out letters,
including different durations, speakers and stop positions.

The defensible conclusion is specific: **with this frozen model, decoder,
postprocessing and reset-per-clip pipeline, 20-second chunks incurred more cleaned
errors than 30-second chunks on this recorded corpus.** This is an observed
accuracy cost of the shorter setting here. It is not proof that the historical
30 → 20 change degraded every workload, nor a historical before/after test of
the original app. Shared prompt rotation across GUI dictations remains a separate
unmeasured state effect; the original current trial is not silently merged into
this reset-baseline matrix.

### Latency tradeoff and paced follow-up without source edits

The earlier 20-second selection was motivated by worst-case Stop-to-text delay:
after Stop the remaining unfinished chunk must drain, and its duration depends on
where Stop falls relative to a cut. Earlier findings used synthetic audio, other
decoder settings (including greedy), and 2x-paced latency measurements; they do
not establish current beam-5/patience-2 latency on these real practice letters.
The present chunk30 runs are offline, with Stop-to-text distributions explicitly
empty/null. Letter offline processing means are 4.942 s at 20-second chunks and
4.514 s at 30-second chunks. Those totals cannot predict paced Stop-to-text delay:
with real-time capture, much of the work can complete while dictation continues.
The 24.832-second letter remains below a 30-second cut, so its entire single chunk
may await Stop at 30 seconds even though offline total compute is lower.

There is an existing source-preserving diagnostic route:
`scripts/latency_bench.py::session` accepts `chunk_s` and `speed` explicitly and
internally uses the real `ChunkedTranscriber`. Parent can call it with an already
loaded, frozen engine and each letter's int16 PCM:

```python
latency_s, max_queue, chunks = latency_bench.session(
    engine, pcm_int16, bundled_style, fresh_pipeline,
    seconds=len(pcm_int16) / 16000, chunk_s=30.0, speed=1.0,
)
```

Use the same call at chunk_s=20.0 as a matched control, fresh bundled-only pipeline
per clip/repeat, existing local model, eight CPU threads, int8_float32, beam 5 and
patience 2. Run sequentially after the parent's current timing work completes;
repeat timing trials to observe jitter and compare matched stop positions, while
keeping repeats distinguished from independent letter recordings. Warmup policy
must match both conditions and be recorded. Apply an outer process timeout because
this existing session helper itself waits without a timeout.

That helper is a **latency diagnostic**, not an exact finite-corpus ASR rerun: it
uses `LoopStream`, which wraps at the audio end and serves complete 1024-frame
blocks; polling and Stop can admit a small amount of repeated initial audio.
It returns latency/queue/chunk counts, not final transcripts. Record that limitation
and do not label its results as exact harness accuracy or schema-1 trial output.
The latency_bench CLI chooses synthetic testdict audio, so its command-line run
alone is not the requested real-letter follow-up.

For exact finite-letter playback, existing `trial_asr.ReplayStream(pcm,
realtime=True)` plus a directly constructed `ChunkedTranscriber(...,
chunk_target_s=30.0)` are available without editing modules. Follow the original
trial's capture-EOF, Stop and drain sequence, and record the actual 30-second
setting in a separate diagnostic artifact. `trial_asr.py`'s public CLI hardcodes
20 seconds both in construction and recorded metadata; there is no supported
--chunk-s flag. Do not monkeypatch it to 30 seconds while retaining its 20-second
label, or rewrite historical fingerprints. Any parent-owned adapter stays inside
ignored results_*, records its own hash plus frozen source/model/corpus inputs and
actual settings, and is not substituted for this matrix's validated run records.

No fingerprinted source or tests were edited for this follow-up. Verification was
read-only run/corpus/source validation and checking the documentation's exact
counts against the parent's saved comparison; the earlier 40 focused tests remain
the harness validation result.

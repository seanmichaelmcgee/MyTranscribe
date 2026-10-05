# MyTranscribe accuracy coordinator: instructions and resumable program

Start with [root onboarding](../../../AGENTS.md), [project SOP](../../PROJECT_SOP.md),
and [optimization instructions](../instructions.md) / [plan index](../readme.md).
Hand these paths to every agent. This is a dated program contract; it does not
replace current human authorization or the live assigned checkpoint.

## Assignment

The user explicitly requested a new Sol 6.1 or Astra coordinating chat, four or
five agents, a more precise optimization specification, and local disk
scratchpads so interrupted work can resume. Use **gpt-6.1-sol / high** for the
coordinator and five workers. Spawn workers with the multi-agent tools, inheriting
the coordinator's model; do not create five user-owned sidebar chats. If five
worker slots are unavailable, queue the remaining role after a completed worker
is closed. Do not silently change models or buy usage resets.

Work in `C:\Users\smich\Documents\Transcription Trials\MyTranscribe`, branch
`claude/festive-einstein-lb2tk9`, existing PR
<https://github.com/seanmichaelmcgee/MyTranscribe/pull/4>. Only this coordinator
owns shared source changes, GPU experiments, final integration, commits and
pushes during this program. Workers own separate local note/prototype folders.
The original chat prepares this handoff and stops editing shared files once the
coordinator starts. The user may steer either chat; checkpoint any changed scope.

The immediate blocking task is already handled: the plan, role instructions,
scratchpad templates and user-supplied external references are on disk. Begin by
reading them and verifying actual local state. While workers investigate distinct
questions, reconcile the reference policy and draft the shared specification;
do not redo their research. Read every worker's evidence before selecting trials.

## Required first reads

- `CLAUDE.md`, `LOCAL_SESSION_HANDOFF.md` (current-state banner; old setup sections
  are historical), `docs/OPTIMIZATION_STATUS.md`, `docs/VOICE_SAMPLE_PLAN.md`.
- This directory's `ACCEPTANCE.md`, `CHECKPOINTS.md`, and `WORKER_COMMON.md`.
- `docs/overnight/2026-10-04-asr-optimization.md`,
  `2026-10-04-whisper-regression-audit.md`, `2026-10-04-whisper-runtime.md`,
  `2026-10-04-prompt-budget.md`, `2026-10-04-phone-010.md`, and
  `2026-10-04-phone-011.md` under `docs/overnight`.
- The local `state.json`, `orchestrator/scratchpad.md`, `references/provenance.json`
  and `references/frontier_transcripts.json` under
  `results_1060/accuracy_program_20261004`.

The user-supplied Frontier AI transcripts are **a separate external-model
comparison source**, not independently listened or human-certified truth. Exact
model, prompts, service settings and whether formatting was inferred are unknown.
Voice 011's external reference says 138/78; Voice 010 says 132/78. The exam says
`changed from prior examination` in 011 and `changed from prior exam` in 010.
Keep historical intended-script scores unchanged and labeled as such. Report
additional external-reference agreement and clinical-field comparisons separately.
Never rewrite an answer key from a local candidate's output or reuse the old
corpus fingerprint for a changed reference. Recognition must not read these files.

Read `references/user_feedback.json` and the later `handoff_updates.jsonl` too.
The user confirmed that the BP differences were speaking variations correctly
transcribed, then clarified that Frontier got both spoken BP values right:
**132/78 for Voice 010 and 138/78 for Voice 011**. Treat both correctly recognized
values as correct; do not present the 011 138-versus-script-132 difference as an
ASR failure. The earlier message naming 132/72 is preserved in feedback history
but superseded for this field by the subsequent clarification. Other external
transcript content still has external-model, not human-certified, provenance.

Before finalizing reference decisions or starting each trial phase, read the local
`handoff_updates.jsonl` if present. The original chat may append a later human
clarification there. Keep the supplied external transcript immutable; construct
and fingerprint a new effective-reference version when human feedback changes a
field. Do not ignore new human evidence merely because a worker already finished.

## Existing machine and evidence

- GTX 1660 Ti, 6 GB. Production is Whisper large-v3, CUDA int8_float32, beam 5,
  patience 2, two CPU threads, 30-second pause-aware chunks. Stop flushes a short
  recording immediately; a 30-second target does not require waiting 30 seconds.
- Installed local Whisper snapshot:
  `C:\Users\smich\.cache\huggingface\hub\models--Systran--faster-whisper-large-v3\snapshots\edaa852ec7e145841d8ffdb056a99866b5f0a478`.
- `venv1060` is the production/comparison environment; `venvmedasr` is isolated.
  Pinned MedASR weights and Google's LM index are already installed under
  `models_medasr/ae1e4845b4b07479735d93e1e591e566435b7104` and
  `models_medasr/language_model/ae1e4845b4b07479735d93e1e591e566435b7104/ngrams.sqlite`.
- Earlier 30 fictional real-headset recordings are in
  `results_1060/real_headset/manifest.json`. Current calibration is 4.7% overall /
  3.1% medical error; it is reused tuning evidence, not general clinical validation.
- Phone data, fixed crops, raw/cleaned outputs and controls are in
  `results_1060/phone_010_20261004` and `results_1060/phone_011_20261004`.
  Neither counts as three independent observations. Reserved personal samples
  09, 12 and 13 remain unused; do not tune on them.
- Whisper copies names/lab values from its style example on both isolated
  approximately-three-second results. Removing all prompts prevents that copying
  but is not a general fix. A five-second minimal-style policy was rejected after
  worsening the older corpus's medical error from 3.1% to 7.1%.
- On 011, VAD bypass reproduces all isolated Whisper transcripts exactly. Lost
  negation, abnormal medical spellings and exertional-to-vaginal errors remain.
  It is about 2.85 dB quieter; genuine whisper versus soft normal voice is unknown.
- MedASR's existing weak beam-8 LM (alpha .1, beta .25) improves exam vocabulary
  on 011 but still misses HGB and emits an age placeholder. LM caches measure
  decoder work only. Fresh paced inference reproduced it at approximately
  .06/.22/.34 seconds for result/exam/letter; these are single observations.
- 451 headless unit tests passed before these report-only changes. Native Windows
  clipboard access was unavailable in this agent session; do not call headless
  tests proof of live clipboard behavior. Ordinary GUI was restored and Ready
  after the phone comparisons. Inspect actual processes rather than stale PIDs.

## Five delegated roles

Spawn one worker for each `workers/01-whisper-prompt.md` through
`workers/05-evaluation.md`. Each reads `WORKER_COMMON.md` and its own role file,
then immediately checkpoints its scratchpad and status on disk. Register each
returned agent ID and actual model/effort in local `state.json` before proceeding.
Delegations are authorized by the user's explicit request. Do not ask the user
again for routine reading, research, local notes or already-authorized scoped fixes.

Workers may inspect source/history, installed package code, ignored fictional
artifacts and official primary technical documentation. They may write CPU-only
prototypes and evidence in their own ignored folders. They may not load GPU
models, alter shared source/reference files, commit/push, close the app, install
packages, record the microphone or send audio anywhere. Separate role folders
avoid conflicts and keep sensitive notes out of Git.

## Phase 1: specification and ranked experiments

Produce `SPEC.md` and `EXPERIMENT_PLAN.md` in this tracked instruction directory,
plus local detailed evidence. The specification must explain the dictation flow
and ownership of capture, acoustic recognition, contextual prompting, correction,
formatting and optional review. Tie each proposed change to one observed failure,
an official mechanism, a falsifiable experiment, expected latency/memory and a
revert condition. Distinguish exact spelling correction from better recognition.
Include offline/security/dependency implications and constraints from ACCEPTANCE.

Rank a small set of concrete avenues rather than a broad parameter sweep:
short-result prompt copying; safe vocabulary/hotword strategies; self-reinforcing
context errors; longer chunk/boundary behavior; faithful CTC/LM decoding and
native-format handling; true whispered acoustics and capture; deterministic
formatting; and a local reviewer as a separately measured experiment. Do not
propose blanket real-word or number/negation substitutions as an accuracy fix.
Do not equate GPU utilization with recognition quality.

The user prefers a lean, inspectable local app, very fast short instructions and
more contextual accuracy for letters/exams. Clipboard is acceptable. A second
workflow toggle is optional only if its measured benefit outweighs interaction
cost. Retain the clean compact UI, clear recording state and actual input meter.
Plan future new fictional samples, mic comparisons and letter-style calibration.

## Phase 2: bounded initial iteration

After the five findings are available, conduct the top one or two justified
experiments using the existing local models/packages. Implementation and scoped
fixes are authorized, but a speculative default swap is not justified by one file.
Prefer isolated opt-in adapters first. Freeze the matrix, references, source,
runtime and model identities before inference. Cap the initial matrix at six
configurations INCLUDING matched controls, not six settings per failure.
Select all configurations before evaluating new results. Do not keep adding
settings merely because a score improved. Research time does not need GPU work.

Run inference sequentially using the existing exclusive lock
`results_medasr/.overnight.lock`, owned-child timeouts and thermal guard. Existing
`overnight_medasr.RunLock`, `Executor`, `ThermalGuard`, and ignored phone
`run_jobs.py` are available; audit actual configuration before reuse. A lock file
remaining on disk does not prove that it is held. Check process ownership and
status before resuming; never launch duplicate GPU work or kill unrelated Python.
Before GPU work, close the idle app gracefully only if its process is identified
and not currently recording. Preserve and restore the ordinary app afterward.

Every runner phase has a fixed start/deadline in its checkpoint, at most 30
minutes, per-child timeout at most 300 seconds unless a predeclared paced corpus
requires a documented bounded increase. Resume must retain that ORIGINAL phase
deadline. The new campaign is distinct from the expired October 3 overnight
window; do not restart old automations. Set an initial active campaign deadline
no later than two hours after coordinator start, persist it, and do not extend
it on resume. Publish the spec, actual results or blockers at that deadline.
The user can explicitly authorize another phase later. No paid reset, automatic
model switch, RunPod rental or remote-machine job is authorized by this plan.

Compare both phone recordings in whole-file and fixed isolated form, and the
older 30-clip corpus as a regression check when relevant. Maintain reference
tracks and evidence limitations. Repeat acoustic arrays are correlated, not new
samples. Check raw and cleaned output, critical terms/values/negation and actual
formatting behavior before judging aggregate WER. Measure Stop-to-formatted-text
through paced real inference for a promising candidate; cached decoder time is
not that measurement. Never silently strip native placeholders or guess age.

If fingerprinted source needs editing, stop owned work first, preserve the old
results, make the scoped fix, run appropriate tests, and regenerate matched
baselines and candidates. Do not mix artifacts from source/reference versions.
Keep `src/gui_qt.py` behavior unchanged. Maintain non-word/unique-match safeguards.
Run the required full `venv1060` test suite before a production code commit, with
headless limitations disclosed. Promote only evidence-supported changes that
meet the acceptance gates; otherwise leave the application at its working default.

## Deliverables and completion

1. Five local findings, source-backed hypotheses and resumable scratchpads.
2. A precise SPEC and predeclared EXPERIMENT_PLAN with implementation order,
   acceptance/revert criteria and the new sample protocol.
3. Revised external-reference agreement alongside historical script scores,
   explicitly labeled, including blood pressure, age, medications and negation.
4. Actual bounded trial results or a clear blocker; no promise of improvement
   without measurements. Include per-workflow timing limits and changed clinical
   words rather than just WER.
5. A concise report in this chat, source change/test evidence, final app state,
   local resume paths, and commits pushed to the existing branch/PR if applicable.

Only publish generalized fictional findings and lean implementation/spec files.
All audio, full external transcripts, detailed hypotheses containing transcripts,
model weights, credentials, environments and trial outputs remain local/ignored.
Update state and next action before ending. Do not message other user-owned chats
or this original chat; the user can read this coordinating chat, and the original
chat can read its status. Finish or checkpoint honestly; a quota pause is not
evidence of success.

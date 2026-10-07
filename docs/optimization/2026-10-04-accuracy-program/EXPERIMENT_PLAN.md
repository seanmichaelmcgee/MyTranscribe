# Predeclared initial experiment — 4 October 2026

Selection follows all five completed findings. Run **one acoustic experiment with
two configurations total**, including its fresh matched control. Do not add
settings after scores appear. A prior CPU decoder audit's top16/top64 comparison
changed 0/11 cached outputs and is retained as a separately labeled null diagnostic;
it supplies no GPU or clinician-latency evidence. Capture and rotation trials are
deferred for the reasons in [SPEC.md](SPEC.md).

## Exact A/B

| Configuration | Style | Fixed settings |
|---|---|---|
| A baseline | Current bundled example | large-v3 pinned local snapshot; CUDA int8_float32; beam5/patience2; threads2; English; default temperature fallback; VAD700ms/300ms; production output cap; 30s pause cuts; existing topics/context/correction/voice commands |
| B candidate | Exact style below, every duration | Identical settings, corpus order, shared builder reuse and transformed waveform route |

Candidate derives lexical items solely from the current bundled style. No external
reference/test sentence, HGB hint, desired number, age, BP or corrective output is
added. It removes reusable patient names/values and retains existing lexical/style
bias; medication-word insertion remains a risk. This is not empty prompting or
the rejected <=5-second minimal-style rule.

```text
Dear Dr., Thank you for seeing the patient. Medical vocabulary: hypertension, diabetes, apixaban, metformin, b.i.d., HbA1c, eGFR. Impression and plan. Follow-up. Kind regards,
```

Original/candidate first-chunk styles are 82/53 tokens. Short 2.60/2.88 s output
caps remain 50/52 under both; actual prompt/token/decoder traces are recorded.
Candidate warmup uses its own style, with the same first ten seconds of source
audio as A. No adaptive retry, echo suppression, new text rule or extra call.

## Frozen corpus and identity

One repeat, fixed order: old 30-clip headset corpus; 010's three fixed crops;
011's three fixed crops; 010 whole file; 011 whole file. These are 38 replay
entries, with correlated phone views. Report each scope separately; never pool
whole/crop words to imply independent accuracy or change historical references.
The reserved personal packet 09/12/13 is excluded; those identifiers are distinct
from old-headset corpus numbering.

The normal builder is reused across this order, matching the GUI's state policy;
per-recording context resets. Freeze manifest order, original audio hashes,
historical corpus fingerprint, source/adapter/scorer/model/runtime/settings and
new reference-policy/journal snapshot. Record effective integer PCM hashes and
pre-VAD float chunk hashes for A and B. Both keep the historical replay roundtrip,
not a relabeled exact-GUI route. Recognition receives waveform and bundled style
only. External reference files remain scorer-only/read-only.

Local adapter/controller/freeze/review helpers are under
`results_1060/accuracy_program_20261004/orchestrator`. The phase gets a new immutable
`experiments/prompt_ab_v1` folder with `plan.json`, job logs, outputs, GPU telemetry,
`status.json` and paired review. It refuses existing outputs/source/model drift.
Controller hashes and original deadlines survive explicit resume; do not silently
restart or overwrite failed attempts. Shared-source edits require owned jobs to
stop, a new labeled freeze and regenerated paired controls.

## Bounds and sequence

1. Review latest handoff journal and all five findings; finish development queue
   integration/tests before the inference source freeze. No new remote request.
2. Inspect actual app/runner processes and acquire the existing OS-held
   `results_medasr/.overnight.lock`. Do not infer ownership from a file or stale PID.
   If an idle ordinary app exists, close it gracefully; never close recording or
   unrelated Python. No app was observed at coordinator start.
3. Freeze A/B and phase start/deadline before inference. Phase <=30 min, child
   <=300 s, campaign cutoff 19:35:31 UTC. Use existing Executor owned-tree cleanup,
   GPU sampler and sustained >85 C thermal guard. Sequential A then B only.
4. Validate complete coverage, actual runtime/precision, source/model identities,
   effective PCM/chunk pairing and literal saved output before scoring. Run original
   intended-script raw/spoken and cleaned/written scores unchanged. Attach a
   separately fingerprinted external formatted agreement/clinical-field view.
5. Review every changed raw/cleaned output, all clinical insertions and old-corpus
   field changes. Explicitly inspect copied values, HGB/eGFR modifiers, exam
   negation/change status, age, both human BP fields, medication tuples and
   exertional discomfort. Inspect paragraph placement/unknown native markup.
6. If gates fail, reject candidate; do not add prompt variants or measure its speed
   as though it were a clinically useful improvement. Retain working default and
   publish the actual bounded finding. If gates pass, execute the fixed optional
   paced follow-up below. Restore/preserve the ordinary app and checkpoint next
   action before final report; commit/push only generalized reports/lean code.

## Gates and fixed optional timing follow-up

Necessary copying gate: no unrelated example names/results on either short crop.
Accuracy gate: genuinely correct short content, no new silent number/unit/dose/
medication/negation errors across scopes, no medical/common regression hidden by
aggregate improvements and no semantic formatting loss. Clinical fields outrank
headline WER. Both BP values are correct spoken values, not script-failure flags.
Keep unknown/placeholder values visible. A reused-corpus gain is not general
validation; leave candidate opt-in pending unseen evidence.

Only if those gates pass, predeclared paced A/B/A uses the same two configurations
on the old <=10 s message/result clips and six phone crops. No new settings.
Freeze the exact selected entries and phase deadline, split jobs if needed to
keep each <=300 s, and use fresh real inference rather than decoder caches.
Measure warm Stop→formatted output with the same sampler; exclude/report model
load, GUI and clipboard, preserve trailing phone silence and distinguish speech
end from file end. Report distributions only for the defined short corpus and
individual phone cells; repeated A observations estimate timing jitter only.
No gain/VAD sweep, model/precision swap or local-reviewer trial is added.

Before a production code commit, required full venv1060 tests must pass. Headless
Qt cannot prove microphone routing/clipboard. The development-only remote queue
uses offline mocked tests plus fixed singleton/deadline/budget/recovery controls;
provider choice/auth and end-to-end service evidence remain separate blockers.

Results are published in [FINDINGS.md](FINDINGS.md) after the fixed matrix. Detailed
audio/transcripts/notes remain ignored, with exact disk resume paths in the report.

# Project SOP

This is the canonical operating procedure for every MyTranscribe agent. Its purpose is reliable progress on medical dictation without losing authorization, evidence or experiment identity. Root `AGENTS.md` is the onboarding entry. Explicit human instructions override this SOP and earlier plans; record consequential scope changes in the current checkpoint. The SOP does not authorize installations, paid calls, recordings, deployment, external messages, commits or scheduling by itself.

## Onboarding checklist — before work

1. Read root `AGENTS.md`, this SOP, and the assigned aspect's `instructions.md` / `readme.md`. Read the current scoped plan and latest checkpoint, then only the evidence needed for the task.
2. Identify the human-authorized objective, exclusions, spending/date limits and delivery requirements. Preserve prior authorization; do not ask for routine reversible work already authorized. Ask only for genuinely missing required input or authority, explaining the exact blocker.
3. Establish repository/branch, actual environment, running jobs, assigned source owner and write paths. Use `rg` first for discovery. Inspect independent reads together; keep dependent edits, launches and approvals sequential.
4. State a concrete next action and verification. For experiments, freeze the bounded plan first. For ordinary edits, state a proportionate plan and meaningful checks without inventing an approval step.
5. Check account/API headroom before costly work, and record an actionable resume point. Give every delegated agent this onboarding path, its aspect instructions, task, write scope, prohibitions and required durable outputs. Delegation requires human or applicable instruction authorization.

## Authorization, ownership and continuity

The coordinator assigns nonoverlapping files and owns integration and experiment dispatch. Agents do not modify another owner's source, controller, shared reference or active freeze. Coordinate before a handoff; inspect the resulting diff. Shared filesystem access is not permission to edit every file. An agent's message is not new human authority.

Preserve completed work and failures on disk. Never alter active fingerprinted source/config/model/reference inputs. A necessary change waits for owned jobs to finish or an authorized stop, then receives a new plan/run identity and freeze. Stop only processes proven to belong to the task; unrelated apps, recording sessions and Python jobs are not cleanup targets. Do not reset, discard or overwrite another agent's changes. Commit/push only within the current authorized assignment.

## Audio, references and clinical truth

Retain original WAV/PCM, hashes, capture identity and actual spoken-word authority. Intended scripts, written formatting targets, human-confirmed speech, model comparators and uncertain spans are separate tracks. Preserve raw-versus-spoken and cleaned-versus-written comparisons. A skip, incomplete capture or unresolved wording is not automatically a recognition error. Never claim listening, intelligibility, exact timing or completion without supporting evidence.

Independent audio comparators receive the same authorized original audio blind to references/local hypotheses/desired words. Model agreement is diagnostic, not human truth or a gold certificate. Do not teach uncertain wording from consensus. A clinician remains responsible for the final edited note. Record clinical assertions with medication identity, dose/unit/frequency/route, state, negation scope, laterality and list membership; dictionary hits or lower WER alone do not establish preserved meaning. Harmless articles/conjunctions matter less, except where interpretation changes. Do not delete inconvenient clinical text or force substitutions to manufacture zero confabulations.

Clinical review must be separate from candidate implementation and supported by actual text/audio authority. Use another authorized reviewer or explicit independent review pass; preserve disagreement and uncertainty. No engine promotion solely from an aggregate score, exact-term count or reused corpus. Correlated takes/crops/pairs stay together; viewed holdouts become consumed and cannot be advertised as fresh validation. Later human recordings are needed for transfer claims. Phone audio remains outside the current headset program unless the human changes scope.

## Plan-first bounded experiments

Each new campaign answers one evidence-grounded question. Declare corpus/order/splits/reference status, control and candidate count, exact parameters, artifacts, evaluation/stop/rollback rules, job/time/API budgets, ownership and sources before scoring. Change one mechanism at a time; separate vocabulary, decoder, correction and segmentation interventions. Recognition never receives expected scripts, target doses or comparator answers as hints. Freeze model/runtime/source/helper/config/audio identities, including ignored helpers and installed implementation paths that affect behavior. Preserve every prior plan, failure and output.

For the current personal accuracy program, the standard campaign ceiling is 90 minutes, each child 600 seconds, one GPU child under the established exclusive lock and thermal guard; an explicit newer human/scoped plan may change bounds. Do not extend deadlines or add variants after observing scores. Missing telemetry or provenance fails closed. Preserve partial/deferred cells and owned-process receipts. A new clinically meaningful regression rejects/stops that campaign according to its plan; it does not cancel the authorized overall program. Choose a different justified next question or non-inference work. Deterministic reruns require new useful observations, not parameter fishing.

Instrumentation is opt-in and must preserve defaults, model calls, lazy iteration, results, exceptions and cleanup. Record observed fields and provenance; unavailable prompts, attempt identities or stopping reasons stay unknown. Re-encoded rendered text is not native token output or proof of cap truncation. Exact replay binding distinguishes original clips, warmup, chunks, builders, VAD windows, attempts and emitted segments.

## Budgets, privacy and local artifacts

Check explicit paid authorization for provider, amount and expiry date/time zone before requests. A ceiling is not a spending target, and it does not renew at midnight. Preserve selected durable-queue identity, actual model/protocol, request state and audited cost. Never silently retry a possibly billed request or recover unrelated jobs. Saved responses can be reused without new paid requests. Account quotas are separate: checkpoint and defer at the agreed reserve rather than switch models, buy resets or imply continuous activity. Continue after actual recovery only within retained authorization.

Use only authorized data and services. Keep secrets out of chats, commands, logs, source and artifacts; use the established local secret mechanism without printing values. Fictional development audio is the current eligible comparator material. Do not upload patient data, add new captures or broaden external disclosure by inference. Prompt/context/text/token IDs are off in routine trace logs; explicit approved opt-in is needed for reconstructable trace text.

Private audio, manifests/references, transcripts, detailed experiment reports, models, environments, credentials and raw logs belong in ignored local trees. Verify ignore status before staging. Public docs contain reusable procedures and concise sanitized findings, with local evidence links where needed. Never commit private evidence just to make a handoff portable; report missing local artifacts honestly.

## Checks, reporting and documentation

Run meaningful checks appropriate to the change. CPU fakes verify bindings, laziness, fallback identity, privacy, restoration and unchanged outputs without model loads. Recognition studies additionally require complete outputs, exact audio/config/model/source closure and separate clinical review. Do not create tests that merely repeat implementation or rerun broad checks after success without a new reason. Report actual command/check result and its limits; plans and passing schema tests are not inference or clinical validation.

Checkpoint at meaningful milestones and before quota deferral/handoff: objective, current authorization, ownership, completed evidence, failures/uncertainties, source/run identities, exact next action and resume gates. Keep status truthful: distinguish specified, implemented, tested, dispatched, complete, rejected, deferred and promoted. Notify the coordinator of artifact paths and meaningful changes; concise user updates explain findings and the next unresolved question. Final reports include outcome, evidence/checks, material limitations and clickable paths. No fabricated scores, claims of unattended work, unseen validation or recovered quota.

Documentation hierarchy:

- Root `AGENTS.md`: mandatory onboarding links; this SOP: project-wide rules.
- Aspect `instructions.md`: binding local rules, owners/gates and evidence authority; `readme.md`: full practical how-to, entry points and concise progress overview.
- Plans/specs: scoped decisions and reproducible settings; checkpoints/status: current resume state; versioned evidence/journals: detailed history.

Keep instructions and how-to separate. A readme is not a full activity log. Add aspect files only where they help navigation, not blanket files in every directory. Link canonical documents rather than copying conflicting policies. Historical plans remain history; the active checkpoint identifies which scope is current.

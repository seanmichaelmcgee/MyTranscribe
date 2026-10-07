# Optimization how-to and plan index

Read [instructions.md](instructions.md) after [project onboarding](../../AGENTS.md). For application setup/use, consult [README_1060.md](../../README_1060.md); for current evidence entry points, consult [OPTIMIZATION_STATUS.md](../OPTIMIZATION_STATUS.md). Historical GPU names and initial defaults are not configuration authority.

## Start or resume work

1. Read the current local checkpoint before choosing a task: [personal continuation](../../results_1060/personal_curriculum/continuation/checkpoint.json) or the checkpoint named by your assigned program. Missing ignored files are not proof that a run completed; obtain the coordinator's scoped handoff.
2. Reconcile current human scope, ownership, actual jobs/lock, sources and account/API authorization. Record the planned next action and allowed writes. Give delegated agents root onboarding plus this aspect's instructions and their exact role.
3. Use existing original-audio evidence, failure reports and human-review queue. Preserve reference authority; a script is not automatically the spoken answer. Implement only the assigned isolated change, with meaningful CPU checks first.
4. If inference is warranted, create a new immutable plan with exact commands, source/helper/model/runtime/input hashes, budget/deadline, clinical review and stop/rollback gates. Dispatch only through the coordinator's owned-process/lock/thermal path. Retain all outputs and receipts.
5. Validate completion/provenance, compare clinical assertions separately from raw/cleaned scores, and save a bounded result. Update the checkpoint and a brief readme/status overview; keep the full history in journals. No automatic winner promotion.

## Agent plan index

| Entry | Purpose |
|---|---|
| [PROJECT_SOP.md](../PROJECT_SOP.md) | Mandatory project-wide procedure |
| [PERSONAL_ASR_CURRICULUM.md](../PERSONAL_ASR_CURRICULUM.md) | Headset curriculum and blind comparator workflow |
| [Public/native trace how-to](whisper-public-trace.md) | Implemented experimental trace interface and limitations |
| [Private results readme](../../results_1060/personal_curriculum/readme.md) | Current local plans, evidence and resume navigation |
| [Ongoing accuracy plan](../../results_1060/personal_curriculum/plans/ACCURACY_CONTINUATION_SPEC.md) | Current personal program bounds and clinical priorities |
| [Trace replay proposal](../../results_1060/personal_curriculum/continuation/TRACE_ONLY_CAMPAIGN_SPEC_v1.md) | Proposed fixed observation replay; not an executable freeze |
| [Binding proposal](../../results_1060/personal_curriculum/continuation/BINDING_LAYER_SPEC_v1.md) | Recording/chunk/builder/warmup identity requirements |
| [Trace clinical review protocol](../../results_1060/personal_curriculum/continuation/TRACE_STUDY_REVIEW_PROTOCOL_v1.md) | Independent exact-output and clinical comparability gates |
| [Dated accuracy-program index](2026-10-04-accuracy-program/ORCHESTRATOR.md) | Historical coordinator/worker specs; use only within their assigned scope |

For that dated program, read [WORKER_COMMON.md](2026-10-04-accuracy-program/WORKER_COMMON.md), [RESUME.md](2026-10-04-accuracy-program/RESUME.md), [ACCEPTANCE.md](2026-10-04-accuracy-program/ACCEPTANCE.md) and the assigned file in `workers/`. Those plans remain auditable history rather than new permission.

## Concise progress overview

The personal program retains both local engines because reviewed failures differ; no clinical winner or new daily default is established. Rejected vocabulary/search attempts and unresolved spoken-word questions remain in local evidence. Trace development is intended to close observation gaps before another Whisper replay. Read the latest checkpoint and trace documentation for implementation/dispatch status; this page is not a live run log. Fresh human recordings are still needed for independent transfer evidence, and expired paid authorization must be renewed explicitly before new spending.

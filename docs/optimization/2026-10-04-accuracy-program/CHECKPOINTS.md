# Disk checkpoint and recovery contract

Local root: `C:\Users\smich\Documents\Transcription Trials\MyTranscribe\results_1060\accuracy_program_20261004`.
All files here are ignored. Instruction/spec files live in this tracked docs
directory. Do not commit raw local state, scratchpads or reference transcripts.

## Ownership

| Path | Sole writer |
|---|---|
| `state.json`, `events.jsonl` | Coordinator |
| `orchestrator/scratchpad.md`, `orchestrator/status.json` | Coordinator |
| `workers/01-whisper-prompt/*` | Worker 01 |
| `workers/02-whisper-regression/*` | Worker 02 |
| `workers/03-medasr-decoder/*` | Worker 03 |
| `workers/04-audio-capture/*` | Worker 04 |
| `workers/05-evaluation/*` | Worker 05 |
| `references/*` | Frozen by original chat; read-only to workers/coordinator |
| `dispatch_receipt.json` | Original chat, written once after dispatch |
| `handoff_updates.jsonl` | Original chat, append-only human clarifications |
| `experiments/*` | Coordinator; each run gets a new immutable ID |

Each role status records `role`, `phase`, `updated_at_utc`, `source_revision`,
`source_hashes_path`, `agent_id` when known, `completed_steps`, `artifacts`,
`next_action`, `blocker`, `last_error` and `findings_complete`. Stages are ready,
researching, prototype_ready, complete, blocked or interrupted. Do not call a role
complete merely because it hit a usage limit. A completed analysis can correctly
conclude that no justified improvement exists.

The coordinator records created/start/deadline times, its actual thread ID,
worker IDs and model/effort, disjoint ownership, retries and whether slots were
closed, phase/source/reference/config hashes, current owned runner PID, original
runner deadline, lock evidence and next runnable action. Write JSON to an owned
temporary sibling and atomically replace the final file. Append timestamped
milestones to scratchpads/events; preserve earlier errors and decision rationale.
Checkpoint before spawning, after registering an ID, before/after each bounded
job, after source/reference version changes and before yielding or ending. A note
should state exactly how the next session can continue without redoing the last
completed step.

## Recovery order

1. Read state, role status, scratchpads and experiment status/logs. Verify Git
   branch, source/config/reference/model/audio fingerprints and original deadlines.
2. Query actual agent status for saved IDs; use existing running workers. Resume
   an interrupted/closed role when supported. Do not assume an old ID is active.
3. If a worker definitively failed or cannot be resumed, start ONE replacement
   for that role with its existing scratchpad, recording the predecessor/retry.
   At most one automatic replacement per role in the initial campaign. Do not
   create two agents writing one folder or repeat completed analyses by default.
4. Check actual owned GPU runner/app processes and try the exclusive lock before
   launching anything. Never infer lock ownership from an on-disk file. If a
   runner remains active, inspect it; do not start another one.
5. Preserve successful artifacts only when all required identities match. Keep
   mismatches in their old directories and start a newly labeled run. Preserve
   the original phase deadline on resume; stop new work after the campaign cutoff.
6. Before source edits, stop owned runner children using the existing cleanup
   behavior. Record completion/failure, then edit/test and regenerate matched
   controls under the new source. Never terminate unrelated apps/processes.
7. If usage is unavailable, checkpoint and allow independent existing local jobs
   to finish their own bounds. Do not buy resets, switch models or claim scheduled
   resumption is configured. Previous overnight automations are paused and expired.

The files provide recoverability, not a guarantee that a disabled agent scheduler
will restart itself. Explicitly report any unresolved scheduling or access blocker.

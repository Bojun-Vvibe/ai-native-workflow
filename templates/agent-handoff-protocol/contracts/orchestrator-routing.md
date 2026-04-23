# Orchestrator routing — canonical table

How the orchestrator MUST react to each `status` value in a worker
handoff. Keep this short; this is the spec the implementing code
must match.

## `status: done`

1. Validate handoff against `handoff.schema.json`. Reject if invalid.
2. Mark `task_id` as completed in mission state.
3. Append `artifacts` to the mission's artifact ledger.
4. Update mission diagnostics (rolling sum of tokens, wall time).
5. If this was the last outstanding task in the mission, transition
   mission to `done`.

## `status: partial`

1. Validate. Reject if invalid (in particular, `continuation` is
   required by the schema for `partial`).
2. Mark `task_id` as `partial-completed`. Do not delete it from the
   work queue.
3. Append `artifacts` to the ledger (the worker did *some* work; keep it).
4. Construct a follow-up task from `continuation.next_task`:
   - Allocate a new `task_id` (do not reuse the parent's).
   - Carry the parent's mission context.
   - Annotate `parent_task_id = <original task_id>` for audit.
   - Apply a per-mission cap: at most N continuations per
     parent task (recommended N=3). On overflow, escalate to a
     human (treat as `unrecoverable` with reason
     `continuation_loop_overflow`).
5. Re-dispatch to a worker. Worker may be the same role/model as
   the parent (recommended) or a different one (only if the
   `continuation.reason` suggests the model was the wrong tool —
   e.g. `context_window_full` may warrant a larger-context model).

## `status: unrecoverable`

1. Validate. `unrecoverable_reason` must be present (schema-enforced).
2. Mark `task_id` as failed. Do *not* re-dispatch automatically.
3. Append `artifacts` (partial work, if any) to the ledger.
4. Escalate:
   - If a human-in-the-loop is configured, page them with the
     handoff's `human_summary` + `unrecoverable_reason`.
   - Otherwise, mark the **mission** as blocked and return.
5. Never silently retry an `unrecoverable`. The worker has
   declared the task as specified is impossible; retrying is
   asking for the same answer.

## Cross-cutting rules

- **Schema validation is non-negotiable.** A handoff that fails
  schema validation is treated as `unrecoverable` with
  `unrecoverable_reason = "handoff_invalid: <validator message>"`.
  The orchestrator does not "try to recover by parsing the prose."
- **Ordering.** Handoffs from concurrent workers may arrive in any
  order. The orchestrator keys off `task_id` to associate; never
  off arrival order.
- **Idempotency.** A worker that re-emits an identical handoff
  (network retry, wrapper restart) must not double-count. Dedupe
  by `(worker_id, task_id, handoff_hash)`.
- **Auditability.** Every handoff is appended to a JSONL ledger
  before any orchestrator action. If the orchestrator crashes, the
  ledger is the recovery source of truth.

# Template: Agent handoff protocol

A typed contract for the **state a worker agent returns to its
orchestrator** at end of task. The worker is constrained to emit a
single envelope with three sections — `status`, `artifacts`,
`continuation` — and the orchestrator's behavior on each `status`
value is defined up front.

The result: the orchestrator never has to "interpret what the
worker meant." If the worker can't satisfy the contract, the
worker says `status: unrecoverable` with a reason, and the
orchestrator routes accordingly.

## Why this exists

Without a handoff contract:

- The worker returns prose. The orchestrator runs a regex over it
  ("did the worker say 'done'?") and sometimes gets it wrong.
- The worker partially succeeds and the orchestrator has no way to
  represent partial success — so it either marks the task done
  (silently losing the unfinished portion) or marks it failed
  (silently losing the finished portion).
- The worker discovers the task as specified is impossible; the
  orchestrator has no slot for "here is a structurally different
  task that *would* succeed."
- Resuming a long-running mission after a crash requires
  reconstructing worker state from logs.

A typed handoff replaces all of this with one schema and three
status values (`done`, `partial`, `unrecoverable`) plus a
`continuation` slot the orchestrator can re-dispatch as a follow-up
task.

## When to use

- Any orchestrator → worker fan-out with ≥2 worker invocations per
  mission.
- Long-running missions where workers may be interrupted (token
  budget hit, agent crash, manual abort) and you want resumption
  semantics.
- Multi-agent (different roles or different model families): a
  uniform handoff protocol means the orchestrator does not branch
  per-worker-type.

## When NOT to use

- One-shot prompts. Overkill.
- The orchestrator and worker are the same loop in the same
  process and share an in-memory state object. The contract
  exists; it just doesn't need a serialization format.
- Free-text, human-consumed outputs (a draft PR description).

## Anti-patterns

- **Binary status (`success` / `failure`).** Real worker outcomes
  are: full success, partial success with a continuation, blocked
  on an external dependency, or "the task as specified is
  impossible — here's what's actually possible." Two values can't
  represent four outcomes.
- **`status: success` with `artifacts: []`.** If the artifact list
  is empty, the worker did not produce anything observable. That's
  not success.
- **Free-form `notes` field that everyone uses for everything.**
  The orchestrator can't reliably parse it. If a piece of
  information is important, give it a typed slot.
- **No `continuation` slot.** Without it, "I made some progress; here
  is what's left to do" can't be expressed. Workers either lie
  ("done") or surrender ("failed") — both lose information.
- **Versionless schema.** When you change the contract, every old
  log entry becomes ambiguous. Always include `protocol_version`.
- **Letting the worker emit the orchestrator's next step.** The
  worker proposes (`continuation`); the orchestrator decides.
  Otherwise the worker is the orchestrator and you have no
  separation of concerns.

## Files

- `contracts/handoff.schema.json` — JSON Schema for the handoff
  envelope. Validate at the worker→orchestrator seam.
- `contracts/orchestrator-routing.md` — the canonical routing
  table: per-status, what the orchestrator does next.
- `examples/done.json` — happy-path handoff.
- `examples/partial-with-continuation.json` — worker hit token
  budget halfway, returns continuation.
- `examples/unrecoverable.json` — worker discovered the task is
  ill-specified.
- `examples/orchestrator-trace.md` — narrative of an orchestrator
  consuming all three handoffs end-to-end.

## The envelope (informal)

```json
{
  "protocol_version": "1.0",
  "worker_id": "implementer-7",
  "task_id": "T-2026-04-23-W08-step-3",
  "status": "done | partial | unrecoverable",

  "artifacts": [
    { "kind": "file", "path": "src/cache.py", "action": "edited" },
    { "kind": "commit", "sha": "8a3f1c2", "message": "fix: ..." }
  ],

  "continuation": {
    "reason": "token_budget_hit",
    "next_task": {
      "instruction": "Continue from line 200 of src/cache.py",
      "context_pointers": ["artifacts[0]", "src/cache.py:200"]
    }
  } ,

  "diagnostics": {
    "tokens_in": 47213,
    "tokens_out": 8842,
    "wall_seconds": 142,
    "tool_calls": 31,
    "cache_hit_rate": 0.74
  },

  "human_summary": "Fixed the lock-acquisition order in evict()."
}
```

## Worked example

See `examples/orchestrator-trace.md` for an end-to-end trace where
an orchestrator dispatches three subtasks, receives one `done`,
one `partial` (re-dispatches the continuation, gets back another
`done`), and one `unrecoverable` (escalates to a human).

## Adapt this section

- Use `contracts/handoff.schema.json` directly with
  [`agent-output-validation`](../agent-output-validation/) at the
  worker→orchestrator seam.
- Decide your `protocol_version` cadence. Bump on any breaking
  change to the schema; never on additive changes.
- Implement `orchestrator-routing.md`'s table in code, not in prose.
  The prose is the spec; the code is the implementation.

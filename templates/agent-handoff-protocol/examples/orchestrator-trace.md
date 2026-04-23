# Orchestrator trace — three subtasks, three outcomes

Mission `M-2026-04-23-W08`. Orchestrator dispatches three subtasks
concurrently to three implementer workers.

## t=0 — dispatch

```
[orchestrator] dispatch
  T-...-step-1 → implementer-7   (fix lock ordering in src/cache.py)
  T-...-step-2 → implementer-8   (replace bare except in src/retry.py)
  T-...-step-3 → implementer-9   (add feature flag for behavior X)
```

## t=142s — first handoff arrives

`implementer-7` returns `done.json`.

```
[orchestrator] handoff received: T-...-step-1 from implementer-7
[orchestrator] schema valid; status=done
[orchestrator] artifacts ledger += [edited src/cache.py, commit 8a3f1c2]
[orchestrator] T-...-step-1 → completed
```

## t=47s — second handoff arrives (out of order)

Wait — `implementer-9` returned at 47s, ahead of step-2.
`unrecoverable.json`.

```
[orchestrator] handoff received: T-...-step-3 from implementer-9
[orchestrator] schema valid; status=unrecoverable
[orchestrator] reason: "Task asks to add a feature flag for behavior X,
                        but src/flags/ does not exist..."
[orchestrator] artifacts ledger += [report investigations/T-...-step-3.md]
[orchestrator] T-...-step-3 → failed
[orchestrator] mission M-2026-04-23-W08 partially blocked
[orchestrator] paging human-in-the-loop with summary + reason
```

The orchestrator does **not** retry. The worker said the task as
specified is impossible; retrying would be asking the same question
and getting the same answer.

## t=488s — third handoff arrives

`implementer-8` returns `partial-with-continuation.json`.

```
[orchestrator] handoff received: T-...-step-2 from implementer-8
[orchestrator] schema valid; status=partial
[orchestrator] continuation present; reason=token_budget_hit
[orchestrator] artifacts ledger += [edited src/retry.py, commit b71e09d]
[orchestrator] T-...-step-2 → partial-completed
[orchestrator] allocating continuation: T-...-step-2.cont-1
[orchestrator] dispatch
  T-...-step-2.cont-1 → implementer-8 (same role/model)
    instruction: "Continue replacing bare 'except:' clauses in
                  src/retry.py. 3 of 7 sites done. Remaining: lines
                  142, 198, 261, 304. Pattern: see line 88."
    parent_task_id: T-...-step-2
```

## t=812s — continuation handoff arrives

`implementer-8` returns `done` for `T-...-step-2.cont-1` with one
more commit covering the remaining 4 sites. Orchestrator marks
`step-2` fully completed (parent + cont chain).

## Final mission state

| task        | status      | continuations | commits |
|-------------|-------------|---------------|---------|
| step-1      | done        | 0             | 1       |
| step-2      | done        | 1             | 2       |
| step-3      | unrecoverable | 0           | 0 (report only) |

Mission state: `partially-done, blocked-on-human` — because step-3
was unrecoverable. The mission does not auto-complete; a human must
re-scope step-3 (or accept it as out of scope) before the mission
can transition.

## Why this is better than free-text handoffs

- **No regex over prose.** Every state transition is driven by a
  schema-validated value.
- **Out-of-order arrivals don't matter.** Routing keys off `task_id`.
- **Partial work is preserved.** Step-2's first commit is in the
  ledger immediately; the continuation completes the work without
  redoing it.
- **`unrecoverable` is a first-class outcome.** The worker can say
  "this task is wrong" without the orchestrator either retrying
  forever (cost) or marking it done (lying).

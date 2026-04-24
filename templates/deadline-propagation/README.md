# deadline-propagation

A single absolute deadline that flows down a nested agent / tool call chain, with each frame reserving a small slack for its own cleanup. Calls that cannot finish in time abort *before* dispatching the next outbound request, so the agent never burns budget on a response it cannot use.

## Purpose

Agent loops naturally fan out: an orchestrator calls a planner, which calls multiple tools, each of which may call a model or HTTP API. Without a shared notion of "how much time is left," each frame either:

- uses a per-call timeout (and the total wall-clock budget silently inflates with depth), or
- has no timeout at all (and one slow leaf hangs the whole mission).

Deadline propagation fixes both: every frame derives its child deadline from the parent's, minus a small `reserve_ms` slack so the parent can always finalize a partial result.

## When to use

- Multi-step agent missions where the *user-visible* budget is wall-clock, not per-call.
- Tool wrappers that fan out to multiple sub-tools and need to return a usable partial result on timeout.
- Any orchestrator that must guarantee it returns *something* (an envelope, a structured error) within the budget — not "eventually, after the last leaf finishes."

## When NOT to use

- Pure batch jobs whose only success criterion is completion (use a job-level timeout, not deadline propagation).
- Single-shot calls with no fan-out — `signal.alarm` or a per-request HTTP timeout is simpler.
- Streaming responses where the value is the partial output — combine with `streaming-chunk-reassembler` instead.

## Anti-patterns

- **Per-call timeouts as the only budget.** A 30s timeout × 4 nested calls = 2 minutes of wall-clock, not 30s.
- **Implicit infinity.** If `deadline=None` is allowed to mean "no limit," it will eventually be passed by accident. The `with_deadline` guard rejects `None`.
- **Zero reserve at every level.** The deepest leaf returns success at exactly `t = deadline`; the orchestrator then has 0ms to assemble its envelope and overshoots. Always reserve ≥ a few ms per frame for finalize.
- **Wall-clock (`time.time()`) instead of monotonic.** NTP adjustments can move wall-clock backward; use `time.monotonic()`.
- **Checking the deadline only at frame entry.** A long-running loop must call `deadline.check()` between iterations, not just once at the top.
- **Catching `DeadlineExceeded` to "retry."** Retrying past the deadline defeats the purpose. Catch it only to assemble a partial result.

## Files

| File | Purpose |
|---|---|
| `deadline.py` | `Deadline` dataclass + `DeadlineExceeded` + `with_deadline` guard. Stdlib only, injectable clock. |
| `example.py` | 3-level nested call chain (orchestrator → planner → tool_a / tool_b) demonstrating reserve, mid-flight check, and partial-result assembly. Uses a fake clock for byte-stable output. |

## Worked example

Run:

```
python3 templates/deadline-propagation/example.py
```

Real stdout (deterministic — fake clock):

```
orchestrator: budget=500ms
planner: start, remaining=450ms
  tool_a: start, remaining=420ms
  tool_a: done,  remaining=340ms
  tool_b: start, remaining=340ms
  tool_b: aborted at step 3 (deadline exceeded before tool_b step 3)
planner: done,  remaining=0ms
orchestrator: outcome=partial, reserve_remaining=19ms

FINAL ENVELOPE:
  outcome: partial
  result: {'a': 'A_RESULT', 'b': None, 'errors': ['tool_b: deadline exceeded before tool_b step 3']}
```

What to notice:

- Orchestrator gets 500ms; planner sees 450ms (50ms reserve).
- `tool_a` gets 420ms (planner's 30ms reserve), finishes in 80ms, succeeds.
- `tool_b` would need 600ms; aborts mid-loop at step 3 once the deadline passes.
- Planner returns at `remaining=0ms` — but the orchestrator still has its 50ms reserve, of which 19ms is left to assemble the envelope. The mission returns `partial` with `tool_a`'s result preserved.

## Integration notes

- Pair with `tool-call-retry-envelope`: pass `deadline.remaining_ms()` as the envelope's `deadline` field so the host can short-circuit retries that cannot finish.
- Pair with `partial-failure-aggregator`: `errors` list above is exactly the shape that aggregator expects.
- For HTTP clients, set `timeout=deadline.remaining_ms() / 1000` on each outbound request *and* call `deadline.check()` immediately before. The double-check catches both "we already timed out before sending" and "the request itself ran long."

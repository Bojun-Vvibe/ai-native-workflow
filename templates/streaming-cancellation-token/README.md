# streaming-cancellation-token

Cooperative cancellation handle for streaming model / tool calls.
Producer polls; consumer signals; cleanups run LIFO with error capture.

## Why this exists

A streamed call cannot just be `kill -9`'d:

- partial bytes are still in the wire / on disk;
- side effects already started (a tool opened a file, the UI showed
  half a message, the cost meter already debited tokens);
- a hard kill leaks every one of those.

Threads/asyncio offer cancellation primitives, but they ride on top of
the framework — there is no portable, stdlib, framework-agnostic
"cooperative stop" value-object you can pass into a sync producer, an
asyncio coroutine, a thread, or a CLI loop and have it Just Work.

This template is that value-object.

## What it guarantees

| Rule | Why |
|---|---|
| `cancel(reason)` is set-once. First reason wins; later calls are ignored. | Audit logs need a stable `reason`; "last writer wins" makes post-mortems fight over which subsystem was actually responsible. |
| Cleanups run LIFO. | They were registered in dependency order (open → flush → debit). Tear-down has to reverse, or you get use-after-free in glue code. |
| A cleanup that raises does NOT abort the rest. | Half-cleanup is worse than slow-cleanup. Each error is captured into `cleanup_errors`; the next cleanup still runs. |
| Cleanups run at most once. | Producer's `finally` AND a belt-and-suspenders caller can both call `run_cleanups()` safely. |
| `register_cleanup` after cancel runs the cleanup *immediately*. | Otherwise a late-registered handler silently leaks its resource. |
| Zero I/O, zero clocks, zero threads. | Token is a pure value-object. Caller decides how to drive the producer (sync loop, asyncio, thread). |

## When NOT to use this

- **You need a deadline** (e.g. "stop after 30s"): use
  [`tool-call-timeout-laddered`](../tool-call-timeout-laddered/). This
  template is event-driven, not time-driven.
- **You need to cancel an already-completed side effect** (refund a
  charge, undelete a file): cleanups run on the *cancel path only* —
  they are not a transaction manager.
- **The producer is uncooperative** (a third-party blocking C call you
  cannot edit): no cooperative token can save you. Use OS-level
  process isolation.

## Files

- `cancel.py` — `CancellationToken`, `Cancelled` exception. ~145 lines,
  stdlib only.
- `example.py` — three runnable scenarios (clean cancel, a raising
  cleanup, late registration). Asserts behaviour; exits non-zero on
  drift.

## Worked example output

```
=== scenario 1: clean mid-stream cancel ===
{"consumer_event": "cancel", "first_call_was_trigger": true,
 "reason_after_two_calls": "user_pressed_escape",
 "second_call_was_trigger": false}
emitted: ['chunk-0', 'chunk-1', 'chunk-2', 'chunk-3']
raised_reason: user_pressed_escape
token_state: {"cancelled": true, "cleanup_errors": [],
              "cleanups_pending": 0, "cleanups_ran": true,
              "reason": "user_pressed_escape"}

=== scenario 2: a cleanup raises; the others still run ===
cleanup_log: ['good_last ran', 'bad_middle entered', 'good_first ran']
cleanup_errors: [('bad_middle', 'RuntimeError: disk full')]

=== scenario 3: register_cleanup AFTER cancel runs immediately ===
fired: ['late_handler ran']

=== all assertions passed ===
```

Run it yourself:

```
python3 example.py
```

## Composition

- **`tool-call-timeout-laddered`** — wires a deadline ladder to
  `cancel(reason="deadline_expired_tier=…")`. This template is the
  cancellation-delivery surface; that one is the policy.
- **`partial-output-checkpointer`** — register `run_finalize_flush` as
  a cleanup so a cancel mid-stream still flushes the in-flight buffer
  to a checkpoint record before tearing down.
- **`agent-decision-log-format`** — log one decision row per cancel
  with `reason`, `cleanups_ran`, `cleanup_errors[*].name`. The
  set-once `reason` invariant is what makes that row diff-able across
  reruns.
- **`structured-error-taxonomy`** — `Cancelled` classifies as
  `do_not_retry` (the human or budget said stop; retrying would
  re-trip the same condition). A cleanup error classifies separately
  per its own type.

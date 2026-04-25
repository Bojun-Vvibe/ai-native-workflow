# tool-call-rate-limit-backpressure

Bounded-queue rate limiter with three explicit submit-time verdicts —
`Admitted`, `Throttled(retry_after_s)`, `Rejected(queue_depth)` — so
agent code is forced to make a load-shedding decision **at submit
time** instead of after a request has silently bloated an in-process
queue. The runtime-control complement to a token-bucket-only limiter
(which lies to you about latency by hiding queueing) and to
`tool-call-circuit-breaker` (which trips on health, not speed).

## When to reach for this

- An agent loop can issue tool calls faster than the tool can serve
  them and you've started seeing latency cliff-edges, OOMs, or
  "everything's queued, nothing's failing" mystery brownouts.
- You want a single chokepoint where you can reason about both
  "am I out of tokens?" (throttle, retry later) and "is the
  downstream so backed up that I should shed this entire request?"
  (reject, bubble up to caller).
- You're building a multi-agent dispatcher that fans calls into a
  shared tool — the dispatcher needs Rejected to propagate as
  "skip this work item, try a different shard" rather than waiting.

## When NOT to reach for this

- You need cross-process / cross-host rate limiting (use a Redis
  token bucket; the algorithm here is the same but the state must be
  shared).
- You need to enforce a per-user quota (combine with
  `tool-permission-grant-envelope`).
- You need health-driven tripping ("this tool keeps 500ing, stop
  trying") — that's `tool-call-circuit-breaker`.

## Files

| File | Purpose |
| --- | --- |
| `limiter.py` | `RateLimitBackpressure` + `Admitted`/`Throttled`/`Rejected` verdicts + `UnknownTicket`. Stdlib only, ~140 lines, no `time.sleep`, no background thread. |
| `example.py` | Four-part runnable worked example. |

## Contract

```python
lim = RateLimitBackpressure(
    rate_per_sec=2.0,
    burst=5,
    queue_capacity=10,
    now_fn=time.monotonic,        # inject a clock for tests
)

verdict = lim.submit()
if isinstance(verdict, Admitted):
    do_the_work()
    lim.complete(verdict.ticket_id)   # MUST be called on success or failure
elif isinstance(verdict, Throttled):
    sleep_or_reschedule(verdict.retry_after_s)
elif isinstance(verdict, Rejected):
    shed_load(verdict.queue_depth, verdict.queue_capacity)
```

Why three verdicts and not "raise on full":

- `Throttled` says "queue has room, just no token — try me back in
  X seconds." Caller backoffs; downstream isn't sick.
- `Rejected` says "queue is *full*; don't even retry me on this
  limiter — go shed load upstream." This is a different semantic
  signal and callers MUST react differently.

`complete(ticket_id)` is explicit on purpose: time-based "in-flight
estimation" is the source of >50% of "we silently doubled our load"
incidents. A failed call must call `complete()` too — failures still
free the slot.

## Composes with

- **tool-call-circuit-breaker** — breaker trips on health
  (failure rate). This trips on speed. Both should fire BEFORE a
  call is made; a calling sequence is `breaker.decide()` →
  `lim.submit()` → tool call → `lim.complete()` → `breaker.record()`.
- **retry-budget-tracker** — once `Throttled` returns,
  the caller's retry attempt MUST consume from the shared retry
  budget so a stuck-throttle does not amplify the brownout.
- **structured-error-taxonomy** — `Throttled` is
  `retryable_after_backoff, attribution=local_pressure`; `Rejected`
  is `caller_shed_load, attribution=local_pressure`; `UnknownTicket`
  is `do_not_retry, attribution=caller_bug`.
- **agent-decision-log-format** — every `Throttled`/`Rejected`
  should be one decision-log record with `exit_state="continue"` and
  the verdict in `tools_called` so the throttling pattern is
  visible across a mission.

## Sample run

Output of `python3 example.py`, copied verbatim:

```

--- Part 1: burst absorbs spike, surplus is Throttled (not silently queued) ---
  submit #1: Admitted ticket=1 depth_after=1
  submit #2: Admitted ticket=2 depth_after=2
  submit #3: Admitted ticket=3 depth_after=3
  submit #4: Admitted ticket=4 depth_after=4
  submit #5: Admitted ticket=5 depth_after=5
  submit #6: Throttled retry_after_s=0.500 depth=5
  submit #7: Throttled retry_after_s=0.500 depth=5
counters: admitted=5 throttled=2

--- Part 2: queue fills, surplus is Rejected (load shed signal) ---
  submit #1: Admitted ticket=1 depth_after=1
  submit #2: Admitted ticket=2 depth_after=2
  submit #3: Admitted ticket=3 depth_after=3
  submit #4: Rejected depth=3/3
  submit #5: Rejected depth=3/3
  submit #6: Rejected depth=3/3
counters: admitted=3 rejected=3

--- Part 3: complete() frees slot + clock advance refills bucket ---
  submit #3 (queue full): Rejected
  submit #4 (slot freed, bucket empty): Throttled retry_after_s=0.500
  submit #5 (after 0.500s wait): Admitted ticket=3
counters: admitted=3 throttled=1 rejected=1 completed=1

--- Part 4: complete(bad_ticket) raises UnknownTicket ---
  double-complete raised: unknown or already-completed ticket: 1
  bogus ticket raised: unknown or already-completed ticket: 99999

All 4 parts OK.
```

The four parts cover, in order: a `burst=5` token bucket admits an
immediate spike of 5 then `Throttled`s the next two with a precise
`retry_after_s=0.5` (deficit 1 token / refill 2 per sec), proving the
limiter never silently queues past the bucket; with a tight
`queue_capacity=3`, the limiter shifts from `Throttled` to `Rejected`
once depth hits capacity — different semantic signal so the caller
sheds load instead of waiting; the `complete()`-then-wait dance shows
that a freed slot alone is not enough (bucket is still empty →
`Throttled`), and only after the clock advances by exactly
`retry_after_s` does the next `submit()` come back `Admitted` (proving
the `retry_after_s` value is honest); double-complete and bogus
ticket-id both raise `UnknownTicket` so a caller bug surfaces loudly
instead of corrupting the queue accounting.

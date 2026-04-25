# retry-budget-tracker

Shared retry budget for tool calls / outbound requests, enforced as a
token bucket so a downstream brownout cannot be amplified by clients
piling on retries.

## Why

A per-call retry cap (e.g. "max 3 retries per request") is not enough.
If 100 callers each get 3 retries during a brownout, the failing
endpoint sees 300 extra requests at the worst possible moment — exactly
when it can least handle them.

The fix is a **shared retry budget**: a small token bucket that all
callers consume from when they retry. When the bucket is empty, retries
are denied even if the per-call cap has not been hit. Callers fast-fail
with `BudgetExhausted` so backpressure propagates immediately.

This is the SRE-book retry budget, distilled to ~80 lines of stdlib
Python with no external deps.

## What's in the box

| File | Purpose |
|---|---|
| `retry_budget.py` | `RetryBudget` (token bucket) + `call_with_budget()` wrapper + `RetryStats`. Thread-safe. |
| `worked_example.py` | 8 concurrent flaky callers sharing one 5-token budget. Verifies the invariant `retries_used <= capacity`. |

## Wire-up

```python
from retry_budget import RetryBudget, RetryStats, call_with_budget, BudgetExhausted

budget = RetryBudget(capacity=20, refill_per_sec=2.0)  # process-wide singleton
stats  = RetryStats()                                  # per service is fine

def fetch():
    return http_get("https://api.example.com/v1/thing")

try:
    body = call_with_budget(fetch, budget=budget, per_call_max=4,
                            stats=stats, backoff_base=0.25)
except BudgetExhausted:
    return cached_or_default()  # propagate backpressure, do not retry harder
```

## Tuning

* `capacity` — burst tolerance. Set to roughly `expected_rps * 0.1`
  so a single bad second cannot exhaust it, but a sustained outage will.
* `refill_per_sec` — steady-state retry headroom. A common rule is
  `0.1 * expected_rps`: at most 10% of traffic may be retries.
* `per_call_max` — keep small (3–5). The shared budget, not this
  number, is the real protection during incidents.

## Worked example output

Run with:

```
python3 worked_example.py
```

Actual output from the included run (8 workers, 60% transient failure,
shared budget capacity=5, refill 1/s, no real sleep):

```
=== per-call outcomes ===
OK   call-0 -> call-0:ok-on-attempt-1
OK   call-1 -> call-1:ok-on-attempt-1
FAIL call-2 -> ConnectionError('call-2: transient blip #5')
DENY call-3 -> shared retry budget empty after 1 retries; last error: ConnectionError('call-3: transient blip #2')
DENY call-4 -> shared retry budget empty after 0 retries; last error: ConnectionError('call-4: transient blip #1')
DENY call-5 -> shared retry budget empty after 0 retries; last error: ConnectionError('call-5: transient blip #1')
DENY call-6 -> shared retry budget empty after 0 retries; last error: ConnectionError('call-6: transient blip #1')
OK   call-7 -> call-7:ok-on-attempt-1

=== aggregate stats ===
attempts        : 8
successes       : 3
failures        : 5
retries_used    : 5
retries_denied  : 4
tokens_remaining: 0.00

invariant OK: retries_used <= capacity (5)
```

Read it as: 3 calls succeeded outright, 1 burned through its per-call
cap, and 4 callers were *denied* retries entirely because earlier
callers had already drained the shared bucket. `retries_used` (5)
exactly matches the bucket capacity — the budget held.

Without the shared budget, those 4 denied callers would each have
issued up to 4 more retries, multiplying load on the failing endpoint
by ~4x at the worst moment. With the budget, they fast-fail and the
caller above them gets a chance to serve cached data or shed load.

## When NOT to use this

* Single-tenant scripts with one logical caller — per-call cap is enough.
* Idempotent reads against a CDN or local cache — retries there are cheap
  and rarely cause amplification.
* When the failure is *not* transient (4xx auth, schema mismatch). Use
  a circuit breaker instead; see `templates/tool-call-circuit-breaker`.

## Related templates

* `tool-call-retry-envelope` — wire format that makes individual retries safe.
* `tool-call-circuit-breaker` — tripping logic for sustained failure.
* `rate-limit-token-bucket-shared` — the same shape, applied to first-tries
  rather than retries.

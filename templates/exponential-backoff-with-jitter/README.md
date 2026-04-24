# `exponential-backoff-with-jitter`

A pure, deterministic *delay planner* for retrying transient failures.
The planner returns the schedule of delays the caller should wait
between attempts; the caller owns the actual sleeping and the actual
call. The split is what makes the policy testable and what lets it
compose cleanly with the other retry-related templates in this
catalog (`tool-call-retry-envelope`, `tool-call-circuit-breaker`,
`deadline-propagation`).

## The problem

Naive `for attempt in range(N): try; except: sleep(2**attempt)` is
the first thing every codebase grows and the first thing every
incident retro tears out. Three things go wrong, in order:

1. **No cap.** A 6-attempt 2^N schedule with `base=1s` reaches 32s
   on the last retry. The caller's user-visible deadline is usually
   30s. Either we hit the deadline mid-sleep and waste the work, or
   we silently exceed it.
2. **No jitter.** When upstream goes down for 60s and 10 000 callers
   all retry on the same `1, 2, 4, 8, 16, 32` schedule, they all hit
   upstream at exactly the same wall-clock instants. The reconnect
   storm reproduces the outage. This is the failure mode the AWS
   Architecture Blog's "Exponential Backoff And Jitter" post
   (2015) was written to kill.
3. **Implicit deadlines.** Sleeping `8s` when the caller's remaining
   budget is `2s` is a bug whether or not the next attempt would
   have succeeded. A sane retry policy is composable with a wall-
   clock deadline; a `time.sleep`-shaped policy is not.

This template solves (1)–(3) with a 70-line stdlib-only planner that
returns a list of `(attempt_index, delay_s)` and a separate
`truncate_to_budget(schedule, budget_s)` that drops trailing retries
that wouldn't fit. Caller still owns the loop.

## Approach

`plan(policy, attempts_total, rng) -> [(attempt_index, delay_s), ...]`

- `attempts_total` is the **total** number of attempts including the
  original. `attempts_total=1` means "no retries" and returns `[]`.
  An `attempts_total=4` plan returns 3 delays — the delay *before*
  retry #1, before retry #2, and before retry #3.
- `rng` is a `random.Random` instance. Inject a seeded one in tests;
  inject `random.SystemRandom()` in production. The planner never
  touches global random state, so two different policies running in
  the same process never interfere.
- `policy.cap_s` is the per-delay ceiling, applied **before** jitter.
  This is the AWS-canonical placement (jitter is computed against
  the capped exponential, not the raw exponential), and it's the
  only placement that prevents a single rare outlier from spending
  the entire budget on one sleep.

Four jitter kinds, named to match the AWS blog so policies are
unambiguous in code review:

| Kind | Formula | When to use |
|---|---|---|
| `none` | `min(cap, base * 2**i)` | Single-caller debugging; never in fan-out. |
| `full` | `uniform(0, min(cap, base * 2**i))` | Default for thundering-herd recovery. Lowest cumulative wait but high variance per-caller. |
| `equal` | `half + uniform(0, half)` where `half = ceiling/2` | When you want at least *some* exponential progression visible per-caller for tracing while still spreading the herd. |
| `decorrelated` | `uniform(base, min(cap, prev_delay * 3))` | Long-running daemons facing a chronically-slow upstream — the random walk avoids both monotonic growth and the long tail of `full`. |

## Contract

- Planner is **pure**: no I/O, no `time.sleep`, no system clock. Two
  calls with the same `(policy, attempts_total, rng-state)` return
  byte-identical schedules. This is the property that makes the
  worked example reproducible across runs (it seeds `Random(7)`).
- `BackoffPolicy` validates at construction: `base_s > 0`,
  `cap_s >= base_s`, `jitter in {"none","full","equal","decorrelated"}`.
  A bad config raises `BackoffConfigError` immediately, not silently
  on the first retry attempt.
- `truncate_to_budget(schedule, budget_s)` only drops from the
  **tail**. The surviving plan is a valid prefix of the original, so
  `attempt_index` numbers stay stable for log correlation.
- `attempt_index` is 0-based and counts retries, not the original
  call. Logging `attempt_index=2` means "the third *retry*", or
  equivalently "the fourth *attempt* overall."
- The planner does **not** decide whether an error is retryable. That
  is the job of `templates/structured-error-taxonomy` (returns the
  `retryability` triple) and `templates/tool-call-retry-envelope`
  (carries `retry_class_hint` on the wire). This template only
  decides *how long to wait* once the caller has decided to retry.

## Usage

```python
from random import SystemRandom
from backoff import BackoffPolicy, plan, truncate_to_budget

policy = BackoffPolicy(base_s=0.25, cap_s=8.0, jitter="full")
schedule = plan(policy, attempts_total=5, rng=SystemRandom())

# Compose with deadline-propagation:
#   remaining_s = deadline.remaining_s()
#   schedule = truncate_to_budget(schedule, remaining_s)

import time
result = call()  # original attempt
for attempt_index, delay_s in schedule:
    if is_terminal(result):
        break
    time.sleep(delay_s)
    result = call()
```

The original call is **outside** the loop. The planner does not return
a delay for attempt 0 because there is no "wait" before the first
call. Wrapping the original in the loop is the most common bug
introduced when adopting this pattern; the structure above prevents
it by construction.

## Composes with

- `tool-call-retry-envelope` — wire-format retry envelope; this template
  generates the *delays between* retries the envelope describes.
- `structured-error-taxonomy` — decides whether to retry at all; this
  template decides how long to wait once the answer is yes.
- `deadline-propagation` — `truncate_to_budget(schedule, deadline.remaining_s())`
  drops retries that wouldn't fit before the deadline.
- `tool-call-circuit-breaker` — when the breaker is `open`, skip the
  entire schedule rather than sleeping then immediately failing.

## Sample run

```
$ python3 templates/exponential-backoff-with-jitter/examples/run_example.py
Scenario A: same (base=0.5, cap=8.0), 6 attempts, four jitter kinds
----------------------------------------------------------------------
  jitter=none          schedule=[(0, 0.5), (1, 1.0), (2, 2.0), (3, 4.0), (4, 8.0)]  cumulative=15.5s
  jitter=full          schedule=[(0, 0.1619), (1, 0.1508), (2, 1.3019), (3, 0.2897), (4, 4.2871)]  cumulative=6.1914s
  jitter=equal         schedule=[(0, 0.331), (1, 0.5754), (2, 1.6509), (3, 2.1449), (4, 6.1435)]  cumulative=10.8457s
  jitter=decorrelated  schedule=[(0, 0.8238), (1, 0.7974), (2, 1.7317), (3, 0.8401), (4, 1.5826)]  cumulative=5.7757s

Scenario B: truncate a 6-attempt 'none' plan to a 5.0s wall-clock budget
----------------------------------------------------------------------
  full plan       = [(0, 0.5), (1, 1.0), (2, 2.0), (3, 4.0), (4, 8.0)]
  fits in 5.0s    = [(0, 0.5), (1, 1.0), (2, 2.0)]
  retries kept    = 3 of 5
  cumulative_kept = 3.5s

Scenario C: attempts_total=1 → no retries, empty plan
----------------------------------------------------------------------
  plan(attempts_total=1) = []
```

Three things to notice in the output above:

1. **Cumulative wait varies enormously by jitter kind even with the
   same policy.** `none` waits 15.5s; `decorrelated` waits 5.8s. If
   you've been using "exponential backoff" without specifying which
   jitter kind, you have not been specifying the policy.
2. **`full` produces a non-monotonic schedule** (`0.16, 0.15, 1.30,
   0.29, 4.29`). That's correct, not a bug — the *expected* delay
   doubles each step, but any individual delay is uniform on
   `[0, ceiling]`. This is exactly the property that breaks up the
   reconnect storm.
3. **Truncation is tail-only.** The 5.0s-budget plan in Scenario B is
   `[(0,0.5), (1,1.0), (2,2.0)]` — the same first three entries as the
   full plan. `attempt_index` numbers are preserved across truncation
   so a log line saying "retry attempt_index=2 succeeded" means the
   same thing whether or not the schedule was truncated.

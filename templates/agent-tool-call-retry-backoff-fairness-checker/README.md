# agent-tool-call-retry-backoff-fairness-checker

Pure stdlib detector that audits an agent's retry timing log to
confirm the retries actually backed off. The failure mode it catches:
the agent hits a transient error, "retries with exponential backoff,"
and on inspection turns out to have hammered the downstream every
~5ms — burning the call budget against a flaky service in seconds,
sometimes triggering rate limiters that then fail the *next* unrelated
call from the same session.

This is a *fairness* check, not a correctness check. It does not care
whether the retries eventually succeeded; it cares whether the retry
policy was honest.

## Why a separate template

Existing siblings cover adjacent concerns:

- `exponential-backoff-with-jitter` — *prescriptive* template that
  describes how to schedule retries. This template is the
  *descriptive* counterpart: given a log of retries that already
  happened, did they actually back off?
- `agent-step-budget-monitor` — counts overall steps / cost;
  doesn't care about inter-retry timing.
- `agent-tool-call-budget-burn-rate-projector` — projects when the
  budget runs out; orthogonal to whether retries were spaced fairly.
- `agent-tool-call-loop-detector` — catches degenerate `(tool, args)`
  repetition. A loop detector fires on *content* (same call over
  and over). This template fires on *timing* — retries can be
  legitimately repeated calls that simply happen too close together.
  Both can fire on the same trace; they answer different questions.
- `agent-retry-argument-drift-detector` — checks that retried args
  match the original args. Different surface (correctness of
  retried payload), same overall family.

## Findings

Deterministic order: `(kind, fingerprint, detail)` — two runs over
the same input produce byte-identical output (cron-friendly diffing).

| kind | what it catches |
|---|---|
| `hot_retry` | first retry delay below `initial_delay_floor_ms` (default 50ms) |
| `flat_or_shrinking` | a consecutive pair of retry delays where the later one is `<=` the earlier one |
| `ratio_below_target` | the ratio between consecutive delays falls outside `[target_ratio - ratio_tolerance, target_ratio + ratio_tolerance]` (defaults: target 2.0, tolerance 0.5 → accept `[1.5, 2.5]`) |
| `too_many_attempts` | a single `(tool, fingerprint)` got more than `max_attempts` total attempts |
| `jitter_floor_violation` | with ≥ 3 retries, *every* consecutive pair of delays differs by less than `jitter_floor_ms` — a sign of lockstep scheduling across replicas (thundering herd risk) |

`ok` is `False` iff any finding fires.

## Design choices

- **First attempt's `delay_before_ms` is ignored.** It's the initial
  scheduling delay, often 0, and not a retry decision. The checker
  audits the timing of *retries*, which is everything from the second
  attempt onward.
- **Per-`(tool, canonical_args)` grouping.** Two unrelated calls to
  `http_get` for different URLs are independent; each gets its own
  retry sequence. Args are canonicalized via sorted-key JSON so
  `{a:1,b:2}` and `{b:2,a:1}` group together.
- **Ratio tolerance is symmetric.** `target_ratio=2.0`,
  `ratio_tolerance=0.5` accepts ratios in `[1.5, 2.5]`. A ratio of
  3.0 (faster-than-prescribed growth) also fires `ratio_below_target`
  — the name is conventional but the check is "outside the band."
  This is intentional: a sudden 10x jump (5ms → 50ms) is also a
  smell, usually meaning the caller fell back to a hardcoded ceiling
  on attempt 2.
- **Zero-delay handling.** A retry with `delay_before_ms == 0`
  preceded by a non-zero delay still fires `flat_or_shrinking`
  (zero ≤ anything positive). A zero-zero pair *also* fires.
  Division-by-zero is avoided: when `prev <= 0` and `cur > 0`, the
  ratio check is skipped (we already reported the structural
  problem, no need to also report `ratio_below_target` against
  infinity).
- **`jitter_floor_violation` requires ≥ 3 retries.** With only two
  retries you can't tell lockstep from one well-spaced pair.
- **Eager refusal on bad input.** Missing keys, wrong types, or
  invalid `outcome` raise `BackoffValidationError` immediately —
  the audit shouldn't pretend a malformed log is healthy.
- **Pure function.** No I/O, no clocks, no transport. The checker
  takes an in-memory list and returns a `FairnessReport`.
- **Stdlib only.** `dataclasses`, `json`, `math`. No `re`, no
  third-party deps.

## Composition

- `exponential-backoff-with-jitter` — write the policy. This
  template — verify the policy was followed.
- `agent-tool-call-loop-detector` — run both. A loop detector fires
  on call repetition; this template fires on retry timing. They
  catch different bugs in the same trace.
- `agent-decision-log-format` — one log line per finding sharing
  `fingerprint` so a reviewer can pivot on the offending tool call.
- `structured-error-taxonomy` — `hot_retry` /
  `flat_or_shrinking` / `jitter_floor_violation` →
  `attribution=tool` (instrumentation bug); `too_many_attempts`
  → `do_not_retry` (the policy already gave up).

## Worked example

Run `python3 example.py` from this directory. Six cases — one clean
exponential progression plus one per finding family. The output
below is captured verbatim from a real run.

```
# agent-tool-call-retry-backoff-fairness-checker — worked example

## case 01_clean_exponential
attempts: 4
{
  "findings": [],
  "ok": true,
  "per_fingerprint": {
    "http_get::{\"url\":\"/x\"}": {
      "attempts": 4.0,
      "retry_delays_ms": [
        100,
        200,
        400
      ]
    }
  }
}

## case 02_hot_retry
attempts: 3
{
  "findings": [
    {
      "detail": "first retry delay 5ms below floor 50ms",
      "fingerprint": "http_get::{\"url\":\"/y\"}",
      "kind": "hot_retry"
    },
    {
      "detail": "retry ratio 40.00 outside [1.50, 2.50]",
      "fingerprint": "http_get::{\"url\":\"/y\"}",
      "kind": "ratio_below_target"
    }
  ],
  "ok": false,
  "per_fingerprint": {
    "http_get::{\"url\":\"/y\"}": {
      "attempts": 3.0,
      "retry_delays_ms": [
        5,
        200
      ]
    }
  }
}

## case 03_flat
attempts: 4
{
  "findings": [
    {
      "detail": "retry delays 100ms -> 100ms (no growth)",
      "fingerprint": "query_db::{\"q\":\"SELECT\"}",
      "kind": "flat_or_shrinking"
    },
    {
      "detail": "retry delays 100ms -> 100ms (no growth)",
      "fingerprint": "query_db::{\"q\":\"SELECT\"}",
      "kind": "flat_or_shrinking"
    },
    {
      "detail": "all consecutive delay diffs [0, 0] below jitter floor 5ms",
      "fingerprint": "query_db::{\"q\":\"SELECT\"}",
      "kind": "jitter_floor_violation"
    }
  ],
  "ok": false,
  "per_fingerprint": {
    "query_db::{\"q\":\"SELECT\"}": {
      "attempts": 4.0,
      "retry_delays_ms": [
        100,
        100,
        100
      ]
    }
  }
}

## case 04_too_many_attempts
attempts: 7
{
  "findings": [
    {
      "detail": "7 attempts exceed max_attempts=5",
      "fingerprint": "flaky::{}",
      "kind": "too_many_attempts"
    }
  ],
  "ok": false,
  "per_fingerprint": {
    "flaky::{}": {
      "attempts": 7.0,
      "retry_delays_ms": [
        100,
        200,
        400,
        800,
        1600,
        3200
      ]
    }
  }
}

## case 05_ratio_off_target
attempts: 4
{
  "findings": [
    {
      "detail": "retry ratio 1.05 outside [1.50, 2.50]",
      "fingerprint": "rpc::{\"m\":\"ping\"}",
      "kind": "ratio_below_target"
    },
    {
      "detail": "retry ratio 1.05 outside [1.50, 2.50]",
      "fingerprint": "rpc::{\"m\":\"ping\"}",
      "kind": "ratio_below_target"
    }
  ],
  "ok": false,
  "per_fingerprint": {
    "rpc::{\"m\":\"ping\"}": {
      "attempts": 4.0,
      "retry_delays_ms": [
        100,
        105,
        110
      ]
    }
  }
}

## case 06_lockstep_jitter
attempts: 4
{
  "findings": [
    {
      "detail": "all consecutive delay diffs [2, 1] below jitter floor 5ms",
      "fingerprint": "upload::{\"f\":\"a\"}",
      "kind": "jitter_floor_violation"
    },
    {
      "detail": "retry ratio 1.01 outside [1.50, 2.50]",
      "fingerprint": "upload::{\"f\":\"a\"}",
      "kind": "ratio_below_target"
    },
    {
      "detail": "retry ratio 1.02 outside [1.50, 2.50]",
      "fingerprint": "upload::{\"f\":\"a\"}",
      "kind": "ratio_below_target"
    }
  ],
  "ok": false,
  "per_fingerprint": {
    "upload::{\"f\":\"a\"}": {
      "attempts": 4.0,
      "retry_delays_ms": [
        100,
        102,
        103
      ]
    }
  }
}
```

Read across the cases: 01 is the only clean trace. 02 catches a
microsecond-fast first retry plus the resulting absurd ratio. 03 is
flat 100ms forever — both `flat_or_shrinking` and lockstep-jitter
trip. 04 simply runs the policy too many times. 05 is the most
common real bug: the agent claims exponential 2x but the observed
multiplier is 1.05 — the backoff exists on paper only. 06 is the
production-incident pattern: delays drift up by 1-2ms across
replicas, never enough to space out the load, and the downstream
takes a coordinated hit.

The output is byte-identical between runs — `_CASES` is a fixed
list, the checker is a pure function, and findings are sorted by
`(kind, fingerprint, detail)` before serialisation.

## Files

- `example.py` — the checker + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.

# agent-tool-call-timestamp-monotonicity-validator

Pure stdlib validator that scans an agent's tool-call trace for
timestamp anomalies that silently corrupt downstream analysis. The
failure mode it catches: a trace is replayed, merged across worker
threads, or stitched together from multiple log shards, and the
timestamps end up out of order. Most analytics tools (latency
histograms, span trees, retry-rate dashboards) *render* such a
trace without warning — the bug is invisible until someone notices
that "this tool call apparently took -8 seconds" or "this agent
session apparently lasted 47 minutes between two adjacent calls,
even though the host was online the whole time."

This is a *temporal sanity* check, not a behavioural check. It
does not care whether the agent did the right thing; it cares
whether the timestamps in the trace are physically possible.

## Why a separate template

Existing siblings cover adjacent concerns:

- `agent-trace-span-orphan-detector` — structural anomalies in a
  span tree (orphans, cycles, multiple roots). Operates on the
  *graph*. This template operates on the *time axis* of the same
  trace and is complementary — a healthy graph with broken
  timestamps still produces nonsense dashboards.
- `agent-tool-call-retry-backoff-fairness-checker` — audits inter-
  retry timing for an exponential-backoff policy. Different
  question: it asks "did the spacing follow the policy?" This
  template asks "is the order physically plausible?"
- `agent-tool-call-loop-detector` — call-content repetition.
  Orthogonal: a trace can have honest content with broken time, or
  broken content with honest time.
- `streaming-checksum-finalizer` — integrity check for streaming
  output. Same spirit (catch silent corruption) on a different
  surface (token stream vs trace metadata).

## Findings

Deterministic order: `(kind, thread, idx, detail)` — two runs over
the same input produce byte-identical output (cron-friendly
diffing).

| kind | what it catches |
|---|---|
| `non_monotonic` | within a single thread, two consecutive calls have `start_ms[i] < start_ms[i-1]` (out-of-order replay / shard merge bug) |
| `duplicate_timestamp` | within a single thread, two consecutive calls share the exact same `start_ms` (log-line collision; ordering now ambiguous) |
| `clock_jump_forward` | within a single thread, a positive gap larger than `max_gap_ms` (default 60s) between consecutive calls (NTP step, laptop sleep / resume, or a missing intermediate event) |
| `negative_duration` | a single call has `end_ms < start_ms` (always a bug; impossible in real time) |
| `future_timestamp` | a call's `end_ms` is greater than the caller-supplied `now_ms` (worker clock drifted ahead of the orchestrator) |

`ok` is `False` iff any finding fires.

## Design choices

- **Per-thread grouping.** A multi-threaded agent *will*
  legitimately interleave timestamps in the global stream — that's
  the entire point of running multiple threads. Flagging cross-
  thread interleaving as out-of-order would produce a deluge of
  false positives. The validator only complains when ordering
  breaks *within a single thread*, which is the only case that's
  actually a bug. Case 02 in the worked example proves this:
  two threads with globally-interleaved starts pass cleanly.
- **Sort by `start_ms`, not by `end_ms`.** Within a thread, calls
  cannot start out of order (a thread is, by definition, sequential).
  `end_ms` ordering is a *consequence* — a long-running call may
  legitimately have a later `end_ms` than a subsequent quick call
  — though this validator's per-thread model assumes synchronous
  call-by-call execution, which is the dominant agent pattern.
- **`now_ms` is optional.** When the trace is being analyzed
  offline (post-mortem, batch eval, retention sweep), there is no
  meaningful "now" — the run already finished. Pass `now_ms=None`
  and `future_timestamp` simply doesn't fire. Pass it for live
  monitoring.
- **`max_gap_ms` defaults to 60s.** Long enough that a slow `bash`
  call (build, test) does not falsely fire; short enough that a
  laptop-sleep gap (typically 5+ minutes) is caught immediately.
  Raise it for environments with legitimate long-running tools;
  lower it if you are confident every operation is sub-second.
- **Eager refusal on bad input.** Missing keys, wrong types, or
  empty strings raise `TimestampValidationError` immediately —
  the audit shouldn't pretend a malformed trace is healthy.
- **Pure function.** No I/O, no clocks, no transport. The
  validator takes an in-memory list and returns a
  `MonotonicityReport`.
- **Stdlib only.** `dataclasses`, `json`. No `re`, no third-party
  deps.

## Composition

- `agent-trace-span-orphan-detector` — run both on every persisted
  trace. They catch structurally and temporally distinct bugs in
  the same artifact.
- `agent-trace-redaction-rules` — apply redaction first, then
  this validator. Redaction must not perturb timestamps; this
  template will surface it if it does.
- `agent-decision-log-format` — one log line per finding sharing
  `(thread, idx)` so a reviewer can pivot directly to the
  offending call in the trace UI.
- `structured-error-taxonomy` — `non_monotonic` /
  `duplicate_timestamp` / `clock_jump_forward` →
  `attribution=tool` (instrumentation / log-pipeline bug);
  `negative_duration` / `future_timestamp` →
  `attribution=tool` (clock skew on the worker); none of these
  warrant retry — the run already happened.

## Worked example

Run `python3 example.py` from this directory. Eight cases — two
clean (single-thread + interleaved-threads) plus one per finding
class plus a combined case that fires three findings in one
thread. The output below is captured verbatim from a real run.

```
# agent-tool-call-timestamp-monotonicity-validator — worked example

## case 01_clean_single_thread
calls: 3  now_ms: 2000
{
  "findings": [],
  "ok": true,
  "per_thread": {
    "T1": {
      "calls": 3.0,
      "first_start_ms": 1000.0,
      "last_end_ms": 1300.0
    }
  }
}

## case 02_clean_interleaved_threads
calls: 4  now_ms: 2000
{
  "findings": [],
  "ok": true,
  "per_thread": {
    "T1": {
      "calls": 2.0,
      "first_start_ms": 1000.0,
      "last_end_ms": 1050.0
    },
    "T2": {
      "calls": 2.0,
      "first_start_ms": 1005.0,
      "last_end_ms": 1300.0
    }
  }
}

## case 03_non_monotonic
calls: 3  now_ms: 2000
{
  "findings": [
    {
      "detail": "start_ms 900 < previous 1000 (tool=edit)",
      "idx": 1,
      "kind": "non_monotonic",
      "thread": "T1"
    }
  ],
  "ok": false,
  "per_thread": {
    "T1": {
      "calls": 3.0,
      "first_start_ms": 1000.0,
      "last_end_ms": 1300.0
    }
  }
}

## case 04_duplicate_timestamp
calls: 2  now_ms: 2000
{
  "findings": [
    {
      "detail": "start_ms 1000 duplicates previous (tool=edit)",
      "idx": 1,
      "kind": "duplicate_timestamp",
      "thread": "T1"
    }
  ],
  "ok": false,
  "per_thread": {
    "T1": {
      "calls": 2.0,
      "first_start_ms": 1000.0,
      "last_end_ms": 1050.0
    }
  }
}

## case 05_clock_jump
calls: 2  now_ms: 100000
{
  "findings": [
    {
      "detail": "gap 90000ms > max_gap_ms 60000 (tool=bash)",
      "idx": 1,
      "kind": "clock_jump_forward",
      "thread": "T1"
    }
  ],
  "ok": false,
  "per_thread": {
    "T1": {
      "calls": 2.0,
      "first_start_ms": 1000.0,
      "last_end_ms": 91500.0
    }
  }
}

## case 06_negative_duration
calls: 1  now_ms: 10000
{
  "findings": [
    {
      "detail": "end_ms 4000 < start_ms 5000 (tool=broken)",
      "idx": 0,
      "kind": "negative_duration",
      "thread": "T1"
    }
  ],
  "ok": false,
  "per_thread": {
    "T1": {
      "calls": 1.0,
      "first_start_ms": 5000.0,
      "last_end_ms": 4000.0
    }
  }
}

## case 07_future_timestamp
calls: 1  now_ms: 5000
{
  "findings": [
    {
      "detail": "end_ms 9999 > now_ms 5000 (tool=drifted)",
      "idx": 0,
      "kind": "future_timestamp",
      "thread": "T1"
    }
  ],
  "ok": false,
  "per_thread": {
    "T1": {
      "calls": 1.0,
      "first_start_ms": 1000.0,
      "last_end_ms": 9999.0
    }
  }
}

## case 08_combined
calls: 4  now_ms: 100000
{
  "findings": [
    {
      "detail": "gap 69200ms > max_gap_ms 60000 (tool=d)",
      "idx": 3,
      "kind": "clock_jump_forward",
      "thread": "T1"
    },
    {
      "detail": "start_ms 1000 duplicates previous (tool=b)",
      "idx": 1,
      "kind": "duplicate_timestamp",
      "thread": "T1"
    },
    {
      "detail": "start_ms 800 < previous 1000 (tool=c)",
      "idx": 2,
      "kind": "non_monotonic",
      "thread": "T1"
    }
  ],
  "ok": false,
  "per_thread": {
    "T1": {
      "calls": 4.0,
      "first_start_ms": 1000.0,
      "last_end_ms": 70500.0
    }
  }
}
```

Read across the cases: 01 is the only single-thread clean trace.
02 proves the per-thread grouping is the right decision — two
threads with starts at 1000, 1005, 1020, 1200 globally interleave
but each thread is internally monotonic, so the validator
correctly passes. 03 is the classic shard-merge bug. 04 is the
"two events landed in the same millisecond bucket and the order
is now ambiguous" case. 05 is the laptop-sleep / NTP-step case
(90s gap between two calls on the same thread). 06 and 07 are
single-call physical-impossibility cases — useful when the
upstream worker has clock drift independent of the orchestrator.
08 is the worst-case shard merge: three intra-thread bugs at
once on the same thread, all surfaced in the deterministic
sort order.

The output is byte-identical between runs — `_CASES` is a fixed
list, the validator is a pure function, and findings are sorted
by `(kind, thread, idx, detail)` before serialisation.

## Files

- `example.py` — the validator + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.

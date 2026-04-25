# agent-trace-span-orphan-detector

Pure stdlib detector for structural anomalies in an agent execution trace
expressed as an in-memory list of spans. Catches the four classes of bug
that silently corrupt trace analysis (Honeycomb / Tempo / Jaeger UIs all
*render* a broken trace without warning, so the operator sees a tidy tree
that is missing branches):

- **`orphan`** — a span's `parent_span_id` references a `span_id` that
  isn't in the input batch
- **`multiple_roots`** — more than one span in the *same* `trace_id`
  has `parent_span_id=None`
- **`cycle`** — following `parent_span_id` chains hits the same span twice
- **`cross_trace`** — a span's parent lives in a *different* `trace_id`

Plus a soft **`dangling_open`** warning (a span has no `finished_at` and
is not the most recent activity in the batch) so a forgotten `span.end()`
surfaces before it poisons your p99 duration math by 6 hours.

## When to use

- Pre-export gate in your trace exporter — drop or quarantine a batch
  before it hits the backend, so the storage layer never holds a tree
  with phantom branches.
- CI assertion on captured fixture traces — a regression in your
  parent-context propagation library shows up as an `orphan` count
  going from 0 to N, *immediately*, instead of weeks later when an SRE
  notices "weird gaps in the waterfall."
- Forensic pass on a single bad trace ID before opening a bug — confirms
  whether the gap you're seeing is a UI issue, an exporter bug, or a
  real instrumentation gap.

## When NOT to use

- This is **not** a full OpenTelemetry validator. It walks four
  structural relationships only — no schema validation of attributes,
  no semantic-convention checks, no time-skew detection. Pair with the
  `otel-cli validate` family if you need those.
- This is **not** a runtime instrumentation library. It's a pure
  function over a list of dicts. Caller decides whether to fail CI,
  drop the trace, or annotate-and-keep.
- It does **not** touch the network or the disk.

## Design choices worth knowing

- **`multiple_roots` is per-trace_id, not per-batch.** A span batch
  routinely contains spans from more than one trace; "two roots in one
  batch" is normal, "two roots inside one trace_id" is the bug.
- **Cycle walk is bounded by `len(spans)`.** A pathological input can
  not push the detector into an infinite loop. The bound is enforced
  with a redundant safety net even after the `seen_in_walk` set check.
- **Findings are sorted `(kind, span_id)`.** Two runs over the same
  input produce byte-identical output, so cron-driven alerting can
  diff yesterday's report against today's without false-positive churn.
- **Duplicate `span_id` raises `TraceValidationError` eagerly.** The
  rest of the analysis would be ambiguous with two spans claiming the
  same id — the *correct* default is to refuse to analyze.
- **`dangling_open` flips `ok=False`.** Forgetting to close a span is
  not "soft" once it lands in storage — it inflates parent durations
  forever. Caller can choose to ignore it by filtering the report's
  `findings` tuple, but the default surfaces it.

## Composes with

- **`agent-trace-redaction-rules`** — redact PII from spans, then run
  this detector on the redacted output (redaction shouldn't change
  parent-id structure; if it does, you have a bug in your redactor).
- **`agent-decision-log-format`** — one log line per `Finding`,
  carrying the same `span_id` field, so a decision log queried by
  `span_id` lights up both layers.
- **`structured-error-taxonomy`** — `orphan` / `cycle` /
  `multiple_roots` map to `attribution=tool` (the instrumentation
  emitter is the bug), `cross_trace` maps to `attribution=user`
  (caller is mixing batches), `dangling_open` maps to
  `attribution=tool` with `retryability=do_not_retry` — the trace is
  already on disk; retrying won't fix it.

## Adapt this section

- `_REQUIRED_FIELDS` — extend if your span model carries more
  mandatory fields (e.g., `service_name`).
- `dangling_open` rule — if your tracer legitimately emits multiple
  in-flight spans at once (long-running parallel work), tighten the
  rule to "no `finished_at` AND `started_at < now - threshold`".

## Worked example

`example.py` runs five synthetic traces — one healthy plus one for
each finding class — and prints one JSON report per case followed by a
batch-wide tally.

### Worked example output

```
========================================================================
01 healthy
========================================================================
{
  "findings": [],
  "ok": true,
  "root_count": 1,
  "span_count": 4
}

========================================================================
02 orphan
========================================================================
{
  "findings": [
    {
      "detail": "parent_span_id='missing-span' not present in trace",
      "kind": "orphan",
      "span_id": "tool1"
    }
  ],
  "ok": false,
  "root_count": 1,
  "span_count": 2
}

========================================================================
03 multiple_roots
========================================================================
{
  "findings": [
    {
      "detail": "trace_id='T3' has 2 roots; expected exactly 1",
      "kind": "multiple_roots",
      "span_id": "rootA"
    },
    {
      "detail": "trace_id='T3' has 2 roots; expected exactly 1",
      "kind": "multiple_roots",
      "span_id": "rootB"
    }
  ],
  "ok": false,
  "root_count": 2,
  "span_count": 3
}

========================================================================
04 cycle
========================================================================
{
  "findings": [
    {
      "detail": "parent chain loops at 'tool1'",
      "kind": "cycle",
      "span_id": "tool1"
    },
    {
      "detail": "parent chain loops at 'tool2'",
      "kind": "cycle",
      "span_id": "tool2"
    }
  ],
  "ok": false,
  "root_count": 1,
  "span_count": 3
}

========================================================================
05 cross+dangling
========================================================================
{
  "findings": [
    {
      "detail": "trace_id='T5' but parent='alien' has trace_id='T-OTHER'",
      "kind": "cross_trace",
      "span_id": "tool1"
    },
    {
      "detail": "span has no finished_at and is not the latest activity",
      "kind": "dangling_open",
      "span_id": "tool2"
    }
  ],
  "ok": false,
  "root_count": 2,
  "span_count": 5
}

========================================================================
summary
========================================================================
{
  "finding_kind_totals": {
    "cross_trace": 1,
    "cycle": 2,
    "dangling_open": 1,
    "multiple_roots": 2,
    "orphan": 1
  }
}
```

Notice case 05: the `alien` span has `trace_id="T-OTHER"`, so it is *not*
flagged as a second root inside `T5` — that would have been the naive
batch-scoped behavior. The detector correctly surfaces only the
`cross_trace` link from `tool1 → alien` and the `dangling_open` on
`tool2`. This is exactly the discrimination the four-rule taxonomy is
designed to give you: a multi-trace batch is normal, a multi-rooted
*trace* is not.

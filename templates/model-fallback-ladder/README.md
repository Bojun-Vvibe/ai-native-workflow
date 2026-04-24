# Template: model-fallback ladder

A pure planner that climbs down an ordered list of model "rungs" until one
succeeds or the ladder is exhausted. Every hop is recorded with a structured
`reason_class` so the mission decision log shows *why* each rung was
abandoned — not just "primary failed, used secondary."

Two distinct skip mechanisms, both observable in the hop trace:

- **Preflight token-budget skip** — if the prompt exceeds a rung's
  `max_input_tokens`, the rung is skipped *without* spending the round-trip.
  Recorded as `reason_class="preflight_too_long"`.
- **Reason-class skip** — if the previous failed rung's `reason_class`
  matches a rung's `skip_on_reason_classes`, the rung is skipped *before*
  being tried (e.g. don't retry a `content_filter` trip on the same vendor's
  smaller model). Recorded as `reason_class="skip_on_reason_class"`.

Stdlib-only Python. The planner takes a `call_fn(rung, prompt) -> outcome`
callable so it does no I/O and is fully deterministic against a mock.

## Why this exists

Production agents need a fallback story: primary model is rate-limited,
secondary should pick up; primary trips a content filter, secondary on the
same vendor will trip too so jump to tertiary; prompt is too long for the
small "cheap fallback" so don't even try it.

Three patterns this replaces:

1. **Single try, raise on error.** Mission dies on a transient `5xx` from one
   provider.
2. **`for model in [a, b, c]: try ... except: continue`.** No skip logic, no
   reason recording, every retry burns a round-trip even when you knew it
   couldn't fit.
3. **Vendor-SDK-specific `with_fallback(...)` chains.** Couples your retry
   policy to one vendor's SDK and produces no replayable trace.

This template gives you a *planner* — a pure function over `(ladder, prompt,
call_fn)` — so the same ladder is testable with a deterministic mock and
auditable from the hop list.

## When to use this

- Multi-provider deployments (vendor A primary, vendor B fallback).
- Same-vendor tier-down ladders (large → medium → small).
- Mixed strategy: try a fast cheap model first, fall back to an expensive
  one only on validation failure (use `reason_class="other"` from your
  validator and chain the ladder under your validator).

## When NOT to use this

- For *retrying the same model* on transient errors — use
  `tool-call-retry-envelope` (idempotency-keyed retry) instead. A ladder hop
  means "give up on this model, try the next one"; a retry means "ask this
  model again."
- For *gating whether to call a model at all* on cost or health grounds —
  use `agent-cost-budget-envelope` and `tool-call-circuit-breaker`. Those
  decide whether to climb onto rung 1; this template decides what happens
  after rung 1 fails.
- When you want the orchestrator to actually pick *the best of several
  parallel responses* — that's a fan-out reducer, use
  `partial-failure-aggregator`.

## Design

### Inputs

`ladder` — ordered list. Each rung:

```json
{
  "id": "primary",                                // required, unique string
  "model": "vendor-a-large",                      // required, opaque to planner
  "max_input_tokens": 200000,                     // optional preflight gate
  "skip_on_reason_classes": ["content_filter"]    // optional skip rules
}
```

`prompt` — opaque dict; planner only reads `tokens_in` (int, optional) for
preflight.

`call_fn(rung, prompt) -> outcome` — caller-supplied. The planner never does
network I/O. Outcome shape:

```json
{ "status": "ok",    "output": <opaque> }
{ "status": "error", "reason_class": "rate_limited"|"context_overflow"|
                                     "5xx"|"timeout"|"content_filter"|"other",
                     "detail": "<optional human note>" }
```

Validation is strict: an `error` outcome with an unknown `reason_class`
raises `ValueError` rather than being silently coerced.

### Algorithm (per rung, in order)

1. **Reason-class skip check.** If a previous rung failed with class `C` and
   this rung's `skip_on_reason_classes` contains `C`, append a `skipped` hop
   with `reason_class="skip_on_reason_class"` and continue to the next rung.
2. **Preflight skip check.** If `prompt.tokens_in` is set and exceeds this
   rung's `max_input_tokens`, append a `skipped` hop with
   `reason_class="preflight_too_long"` and continue. *Preflight skip does
   NOT update `last_failure_class`* — we never tried this rung, so the next
   rung shouldn't react as if this rung produced a class.
3. **Call.** Run `call_fn`. On `ok`, append the hop and return verdict
   `ok`. On `error`, append the hop, update `last_failure_class`, and
   continue.
4. If all rungs are consumed, return verdict `exhausted` with the full hop
   trace.

### Determinism

- Hops are emitted in ladder order.
- Same `(ladder, prompt, mock_outcomes)` → byte-identical JSON output.
- Validation errors fire on bad input shape *before* any rung is tried.

## Layout

```
templates/model-fallback-ladder/
├── README.md
├── bin/
│   └── plan.py               # pure planner + CLI; no deps
└── examples/
    ├── 01-primary-rate-limited-secondary-ok/
    └── 02-context-overflow-skips-rung/
```

## Worked example 1 — primary rate-limited, secondary takes over

3-rung ladder, primary returns `rate_limited`, secondary returns `ok`. The
tertiary rung is never tried.

```bash
./bin/plan.py examples/01-primary-rate-limited-secondary-ok/ladder.json \
              examples/01-primary-rate-limited-secondary-ok/prompt.json \
              examples/01-primary-rate-limited-secondary-ok/mock_outcomes.json
```

Verified stdout (exit code **0**):

```json
{
  "verdict": "ok",
  "winning_rung_id": "secondary",
  "winning_output": {
    "text": "answer-from-secondary"
  },
  "hops": [
    {
      "rung_id": "primary",
      "model": "vendor-a-large",
      "outcome": "error",
      "reason_class": "rate_limited",
      "detail": "retry-after=37s"
    },
    {
      "rung_id": "secondary",
      "model": "vendor-b-large",
      "outcome": "ok",
      "reason_class": null,
      "detail": null
    }
  ],
  "rungs_tried": 2,
  "rungs_skipped": 0
}
```

Note `rungs_tried=2`, not 3 — the trace is the audit trail, not just the
verdict.

## Worked example 2 — content_filter trip skips same-vendor rung; tertiary preflight-skipped; ladder exhausted

This example demonstrates **both** skip mechanisms and an `exhausted`
verdict. Three rungs:

- `primary` (vendor-a-large, 200k cap)
- `secondary` (vendor-a-medium, 128k cap, `skip_on_reason_classes=["content_filter"]`)
- `tertiary` (vendor-c-small, 32k cap)

The 48k-token prompt fits primary and secondary but not tertiary. Primary
trips `content_filter`. Secondary is *not* called — it's the same vendor and
declared it shouldn't be retried on `content_filter`. Tertiary is *not*
called either — preflight rejects 48000 > 32000. Ladder exhausts.

```bash
./bin/plan.py examples/02-context-overflow-skips-rung/ladder.json \
              examples/02-context-overflow-skips-rung/prompt.json \
              examples/02-context-overflow-skips-rung/mock_outcomes.json
```

Verified stdout (exit code **1**):

```json
{
  "verdict": "exhausted",
  "winning_rung_id": null,
  "winning_output": null,
  "hops": [
    {
      "rung_id": "primary",
      "model": "vendor-a-large",
      "outcome": "error",
      "reason_class": "content_filter",
      "detail": "policy=p4 segment=intro"
    },
    {
      "rung_id": "secondary",
      "model": "vendor-a-medium",
      "outcome": "skipped",
      "reason_class": "skip_on_reason_class",
      "detail": "previous_failure=content_filter"
    },
    {
      "rung_id": "tertiary",
      "model": "vendor-c-small",
      "outcome": "skipped",
      "reason_class": "preflight_too_long",
      "detail": "tokens_in=48000 max_input_tokens=32000"
    }
  ],
  "rungs_tried": 1,
  "rungs_skipped": 2
}
```

Both skipped hops carry distinct `reason_class` values (`skip_on_reason_class`
vs `preflight_too_long`), so a downstream cost report can correctly attribute
the failure to "ladder exhausted because nothing else fit / was eligible"
rather than misreporting two extra round-trips that never happened.

## Composes with

- **`tool-call-retry-envelope`** — wrap `call_fn` so each rung's call is
  itself idempotency-keyed and safely retryable on a transient blip *before*
  giving up on that rung.
- **`agent-cost-budget-envelope`** — pre-flight a budget check inside
  `call_fn` so an over-budget rung returns `error` with `reason_class="other"`
  and the ladder climbs down to a cheaper rung.
- **`agent-decision-log-format`** — append the full `hops` array as one
  decision-log entry per mission step so a replay shows every rung that was
  tried or skipped and why.
- **`partial-failure-aggregator`** — orthogonal: this template handles "try
  models in order until one works"; the aggregator handles "fan out to N
  things in parallel and reduce."

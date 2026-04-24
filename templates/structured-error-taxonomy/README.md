# structured-error-taxonomy

Pure classifier that turns a raw error record (from a model call, a tool
call, or a host-side failure) into a canonical
`(class, retryability, attribution)` triple drawn from a small, stable
enum so downstream runtime-control templates can branch on the *class*
instead of fragile substring matching against vendor messages.

Composes with:

- [`templates/model-fallback-ladder`](../model-fallback-ladder/) — the
  ladder's `reason_class` is exactly the `class` field this template
  emits, so a `content_filter` verdict here drives a same-vendor skip
  there.
- [`templates/tool-call-retry-envelope`](../tool-call-retry-envelope/) —
  the envelope's `retry_class_hint` should be set to the `retryability`
  field this template emits, so the host-side dedup table can refuse to
  even attempt a `do_not_retry` call.
- [`templates/tool-call-circuit-breaker`](../tool-call-circuit-breaker/)
  — only failures with `attribution=tool` should count toward a tool's
  failure rate; `attribution=caller` failures (bad input, auth) must
  not trip the breaker.
- [`templates/agent-cost-budget-envelope`](../agent-cost-budget-envelope/)
  — a `quota_exhausted` verdict means do not climb to a more expensive
  rung; degrade or kill instead.

## Why

When errors are matched by raw vendor message, three things go wrong:

1. **Vendor wording drifts.** "Rate limit reached" becomes "Too many
   requests, please slow down" in a minor SDK update; every downstream
   `if "rate limit" in str(e)` quietly stops working.
2. **Different layers misclassify the same failure.** The retry layer
   thinks a `400` is retryable transient; the circuit breaker thinks
   it's a tool failure; the cost layer thinks it was billed. They
   should all see the same canonical class.
3. **`unknown` is silently treated as "ok to retry"**, burning budget on
   genuinely terminal errors.

This template fixes all three by making classification a single pure
function with a deterministic catch-all.

## What

- `bin/classify_error.py` — stdlib-only Python classifier. Reads JSONL
  on stdin or `--in`, writes one verdict per input line, exits 0 if
  every input matched a non-default rule, 1 if any input fell through to
  `unknown`, 2 on malformed input.
- `SPEC.md` — the three enums (`CLASSES`, `RETRYABILITY`,
  `ATTRIBUTION`) and the rule-evaluation contract.
- `prompts/add_rule.md` — strict-JSON prompt for proposing a new rule
  (rule_id, predicate sketch, verdict triple) when triage flags a
  recurring `unknown`.
- `examples/` — two end-to-end runs.

## When

- You have at least three different layers of code (retry, circuit
  breaker, cost) all branching on error shape.
- You are about to introduce a model-fallback ladder and want its
  `skip_on_reason_classes` to mean the same thing every layer means.
- Your decision logs already store a `vendor_code` and you want to add a
  `class` field that survives vendor wording drift.

## Worked example 01 — clean batch (exit 0)

Six raw errors covering each major class. Every input matches a
non-default rule, so the run exits 0.

```bash
$ ./bin/classify_error.py --in examples/01-classify-clean-batch/input.jsonl
{"attribution": "vendor", "class": "rate_limited", "id": "call-1", "matched_rule": "rl_429", "retryability": "retry_after"}
{"attribution": "caller", "class": "content_filter", "id": "call-2", "matched_rule": "content_filter", "retryability": "do_not_retry"}
{"attribution": "tool", "class": "tool_timeout", "id": "call-3", "matched_rule": "tool_timeout", "retryability": "retry_after"}
{"attribution": "host", "class": "host_io", "id": "call-4", "matched_rule": "host_io", "retryability": "do_not_retry"}
{"attribution": "caller", "class": "auth", "id": "call-5", "matched_rule": "auth_401_403", "retryability": "do_not_retry"}
{"attribution": "caller", "class": "context_length", "id": "call-6", "matched_rule": "context_length", "retryability": "retry_with_edit"}
$ echo $?
0
```

Note `call-5` (auth) and `call-2` (content_filter) both get
`retryability=do_not_retry` even though the surface symptoms (HTTP 401
vs vendor `content_policy_violation`) are nothing alike — that's the
point of the canonical enum.

## Worked example 02 — unknown class detected (exit 1)

Three errors; the middle one uses a vendor code the rule table doesn't
know about. The classifier still returns a verdict (catch-all
`unknown`/`do_not_retry`/`unknown`) but exits 1 so a CI gate or triage
job can surface it.

```bash
$ ./bin/classify_error.py --in examples/02-detect-unknown-class/input.jsonl
{"attribution": "vendor", "class": "transient_network", "id": "call-A", "matched_rule": "net_5xx", "retryability": "retry_after"}
{"attribution": "unknown", "class": "unknown", "id": "call-B", "matched_rule": "default", "retryability": "do_not_retry"}
{"attribution": "caller", "class": "tool_bad_input", "id": "call-C", "matched_rule": "tool_bad_input", "retryability": "retry_with_edit"}
$ echo $?
1
```

The `unknown` verdict is the *correct* default: better to refuse to
retry an error you don't understand than to burn budget retrying a
terminal one. Triage can then run `prompts/add_rule.md` against a
recent batch of `default`-matched records to propose new rules.

## Layout

```
structured-error-taxonomy/
├── README.md
├── SPEC.md
├── bin/
│   └── classify_error.py
├── prompts/
│   └── add_rule.md
└── examples/
    ├── 01-classify-clean-batch/
    │   ├── input.jsonl
    │   ├── output.jsonl
    │   └── exit.txt
    └── 02-detect-unknown-class/
        ├── input.jsonl
        ├── output.jsonl
        └── exit.txt
```

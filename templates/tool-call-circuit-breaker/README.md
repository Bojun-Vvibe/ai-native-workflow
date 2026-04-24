# Template: tool-call-circuit-breaker

A per-tool circuit breaker that lives on the agent host and gates
every tool call through a small state machine: `closed -> open ->
half_open -> closed`. When a tool's failure rate in a recent window
crosses a configured threshold, the breaker trips and short-circuits
subsequent calls with a deterministic `denied_open` decision — no
upstream traffic, no retry storms, no "the agent kept hammering the
broken backend for ninety seconds because each individual call site
thought it was fine."

This is the runtime-control complement to `tool-call-retry-envelope`
(which makes individual calls safely retryable) and
`agent-cost-budget-envelope` (which gates calls on cost). Retry says
"this one call can be re-attempted." Budget says "you cannot afford
this call." Circuit breaker says **"this tool itself is unhealthy
right now; do not call it at all."**

## Why this exists

Three failure modes that a per-call retry envelope cannot solve on
its own:

1. **Retry storm against a degraded backend.** The retry envelope
   says "this call is idempotent, retry it." Five concurrent agent
   loops each retry their failed call three times. The flaky search
   backend is now taking 15 calls per second per loop instead of
   the usual 1. The breaker collapses that to zero by short-circuiting
   at the agent host before the request leaves.
2. **Slow-fail amplification.** Each individual failed call takes
   30 seconds to time out. Without a breaker, the agent burns 30s of
   wall clock and one tool-call slot per attempt. With a breaker
   open, denials are O(1) and the agent can pick a fallback tool or
   surface a structured failure immediately.
3. **Recovery without flooding.** When the backend comes back, you
   want one or two probe calls to verify, not "all five concurrent
   agent loops simultaneously fire their retries the moment the
   cooldown ends." Half-open with `probe_max_concurrent=1` enforces
   this.

## When to use

- Your agent calls upstream tools (HTTP APIs, databases, search
  backends, code-execution sandboxes) that can become unhealthy.
- You already have retry logic and want to bound the *outer*
  behavior — "stop trying entirely for a minute" — independently of
  per-call retry.
- You want a deterministic, replayable signal for "this tool is
  unhealthy" that you can route on (pick a fallback, surface to user,
  log as a host-level event).

## When NOT to use

- The tool has its own circuit breaking at the SDK or service-mesh
  layer (Envoy, Istio, gRPC client interceptors). Don't double-break;
  you'll get correlated trip windows that mask each other's signals.
- The tool is called once per agent session. The window will never
  fill; the breaker will never trip; you've added complexity for no
  benefit. Use a simple per-call timeout.
- Failures are dominated by per-input errors (e.g. "this query is
  malformed"). Those are *not* tool health signals — they're caller
  errors and should not contribute to the failure rate. Filter them
  out before recording.

## What's in the box

| File | What it does |
|---|---|
| `SPEC.md` | Wire spec: state machine, transitions, policy schema, decision schema, event-log replay format, anti-patterns |
| `bin/circuit_breaker.py` | Stdlib-only reference engine. `decide(policy, state, now, tool) -> Decision`; `record(policy, state, now, outcome) -> Transition`; CLI replays a JSONL event log |
| `prompts/breaker-trip-explainer.md` | Strict-JSON prompt that turns a `denied_open` decision into a one-paragraph user-facing explanation suggesting a fallback path |
| `examples/01-trip-on-failure-rate/` | Worked example: five calls (one success, four failures) trip a `min_calls=5, threshold=0.5` policy; subsequent calls are denied with `cooldown_remaining_s` |
| `examples/02-half-open-recovery/` | Worked example: an open breaker waits out a 10s cooldown, allows two consecutive probe successes in `half_open`, closes, and resets the failure window |

## Adapt this section

Edit the policy you ship to `bin/circuit_breaker.py`:

```json
{
  "window_size": 20,
  "min_calls": 5,
  "failure_rate_threshold": 0.5,
  "cooldown_seconds": 30.0,
  "probe_max_concurrent": 1,
  "probe_required_successes": 2
}
```

Tuning rules of thumb:

- `min_calls` should be at least `1 / failure_rate_threshold` so a
  single failure cannot trip the breaker.
- `cooldown_seconds` should be longer than your tool's typical
  recovery time (deploy rollout, cache warmup, secondary failover).
- `probe_max_concurrent=1` is almost always right. Raise only if
  your tool genuinely needs concurrent traffic to recover.
- Maintain one breaker per tool, not one per call site. The state is
  cheap; the operational clarity is worth it.

## Contract

The agent host owns one `BreakerState` per tool. For every tool
call:

1. Call `decide(policy, state, now(), tool)`.
2. If `decision == "allow"` or `"allow_probe"`: dispatch the call,
   then call `record(policy, state, now(), outcome)` with the result
   classified as `"success"` or `"failure"`.
3. If `decision == "denied_open"`: do **not** dispatch. Either pick a
   fallback path (other tool, cached response, degraded answer) or
   return a structured failure to the caller. Do not record an
   outcome for a denied call.

The reference engine takes the clock as a parameter so missions
that replay a JSONL event log produce bit-exact decision streams —
useful for unit tests and for "explain why the breaker tripped at
14:32" forensics.

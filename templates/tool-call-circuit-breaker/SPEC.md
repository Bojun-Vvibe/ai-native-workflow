# SPEC: tool-call-circuit-breaker

## Wire model

A circuit breaker is keyed per `tool` (e.g. `web_search`, `db_query`,
`code_search`). Each tool has its own independent state. Breakers are
**not** shared across tools — a flapping search backend should not
stop the agent from calling the database.

## States

| State | Meaning | Allowed |
|---|---|---|
| `closed` | Normal. Window of recent outcomes is being tracked. | All calls |
| `open` | Breaker has tripped. Calls short-circuit. | None until cooldown elapses |
| `half_open` | Cooldown elapsed. Limited probe calls allowed to test recovery. | At most `probe_max_concurrent` probes |

## Transitions

```
closed --(failure_rate >= threshold AND window >= min_calls)--> open
open --(now - opened_at >= cooldown_seconds)--> half_open
half_open --(probe_required_successes consecutive probe successes)--> closed
half_open --(any probe failure)--> open  (cooldown reset)
```

## Policy schema

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

| Field | Meaning |
|---|---|
| `window_size` | Max number of recent outcomes kept in the rolling window. |
| `min_calls` | Don't trip until the window has at least this many samples. |
| `failure_rate_threshold` | Trip when `failures / window_len >= this`. |
| `cooldown_seconds` | How long `open` lasts before moving to `half_open`. |
| `probe_max_concurrent` | Max in-flight probes in `half_open`. |
| `probe_required_successes` | Consecutive probe successes needed to close. |

## Decision schema

`decide(policy, state, now, tool)` returns:

```json
{
  "decision": "allow" | "allow_probe" | "denied_open",
  "state": "closed" | "open" | "half_open",
  "tool": "web_search",
  "reason": "breaker_closed" | "probing_recovery" | "cooldown_active" | "probe_slots_exhausted",
  "failure_rate": 0.6,
  "window_size": 10
}
```

`open` decisions also include `cooldown_remaining_s`. Half-open denies
include `probes_in_flight`.

## Outcome recording

After every call attempt that was allowed (`allow` or `allow_probe`),
the caller MUST record the outcome with `record(policy, state, now,
outcome)` where `outcome ∈ {"success", "failure"}`.

In `closed`: appended to window; may transition to `open`.
In `half_open`: decrements `probes_in_flight`; success advances
counter, failure re-trips and resets cooldown.

## Determinism rules

- Clock is injected (`now: float`). The reference engine never reads
  the wall clock itself — replays from a JSONL event log are bit-exact.
- The window is `collections.deque` with `maxlen` enforced manually so
  that `window_size` changes between calls are honored.
- A probe failure does NOT contribute to the closed-window failure
  rate (the window is cleared on close anyway). This avoids double
  counting: the probe outcome already drove the half_open transition.

## Event log (for replay / audit)

The CLI consumes a JSONL stream of three event kinds:

```jsonl
{"ts": 100.0, "tool": "web_search", "event": "call_attempt"}
{"ts": 100.1, "tool": "web_search", "event": "failure"}
{"ts": 105.0, "tool": "web_search", "event": "success"}
```

`call_attempt` emits a decision; `success` / `failure` emit a state
transition record. The two are paired by the caller.

## Anti-patterns

- **Sharing one breaker across all tools.** A single flaky tool will
  block the rest of the agent.
- **Counting agent-side cancellations as failures.** Only count
  upstream errors (HTTP 5xx, timeouts, empty mandatory results).
  Treat user-cancelled or budget-denied as neither success nor
  failure — don't record.
- **Tiny windows with high thresholds.** `window_size=3,
  failure_rate_threshold=0.66` means two failures in a row trip the
  breaker — too jumpy. Pair `min_calls` with `window_size`.
- **No upper bound on `probe_max_concurrent`.** Defeats the purpose of
  half-open; you'll re-flood a recovering backend.

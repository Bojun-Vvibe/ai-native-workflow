# Example 02 — half-open probe recovery

## What this shows

The `db_query` tool fails five times in a row, tripping the breaker
to `open` at `ts=204.1`. A call attempt at `ts=206.0` (before
cooldown) is denied. After `cooldown_seconds=10` elapses, the call
attempt at `ts=215.0` is allowed as a probe (state moves to
`half_open`). The probe succeeds. A second probe at `ts=216.0` also
succeeds. With `probe_required_successes=2` met, the breaker closes
and the window is reset. The next call at `ts=217.0` is a normal
`allow` with a fresh `failure_rate=0.0, window_size=0`.

## Policy

```json
{
  "window_size": 10,
  "min_calls": 5,
  "failure_rate_threshold": 0.5,
  "cooldown_seconds": 10.0,
  "probe_max_concurrent": 1,
  "probe_required_successes": 2
}
```

## Run

```bash
python3 ../../bin/circuit_breaker.py demo policy.json events.jsonl
```

## Verified output

```jsonl
{"decision": "allow", "event": "call_attempt", "failure_rate": 0.0, "reason": "breaker_closed", "state": "closed", "tool": "db_query", "ts": 200.0, "window_size": 0}
{"event": "outcome", "failure_rate": 1.0, "outcome": "failure", "state_after": "closed", "tool": "db_query", "transition": "closed->closed", "ts": 200.1, "window_size": 1}
{"decision": "allow", "event": "call_attempt", "failure_rate": 1.0, "reason": "breaker_closed", "state": "closed", "tool": "db_query", "ts": 201.0, "window_size": 1}
{"event": "outcome", "failure_rate": 1.0, "outcome": "failure", "state_after": "closed", "tool": "db_query", "transition": "closed->closed", "ts": 201.1, "window_size": 2}
{"decision": "allow", "event": "call_attempt", "failure_rate": 1.0, "reason": "breaker_closed", "state": "closed", "tool": "db_query", "ts": 202.0, "window_size": 2}
{"event": "outcome", "failure_rate": 1.0, "outcome": "failure", "state_after": "closed", "tool": "db_query", "transition": "closed->closed", "ts": 202.1, "window_size": 3}
{"decision": "allow", "event": "call_attempt", "failure_rate": 1.0, "reason": "breaker_closed", "state": "closed", "tool": "db_query", "ts": 203.0, "window_size": 3}
{"event": "outcome", "failure_rate": 1.0, "outcome": "failure", "state_after": "closed", "tool": "db_query", "transition": "closed->closed", "ts": 203.1, "window_size": 4}
{"decision": "allow", "event": "call_attempt", "failure_rate": 1.0, "reason": "breaker_closed", "state": "closed", "tool": "db_query", "ts": 204.0, "window_size": 4}
{"event": "outcome", "failure_rate": 1.0, "outcome": "failure", "state_after": "open", "tool": "db_query", "transition": "closed->open", "ts": 204.1, "window_size": 5}
{"cooldown_remaining_s": 8.1, "decision": "denied_open", "event": "call_attempt", "failure_rate": 1.0, "reason": "cooldown_active", "state": "open", "tool": "db_query", "ts": 206.0, "window_size": 5}
{"decision": "allow_probe", "event": "call_attempt", "failure_rate": 1.0, "probes_in_flight": 1, "reason": "probing_recovery", "state": "half_open", "tool": "db_query", "ts": 215.0, "window_size": 5}
{"consecutive_probe_successes": 1, "event": "outcome", "outcome": "success", "state_after": "half_open", "tool": "db_query", "transition": "half_open->half_open", "ts": 215.1}
{"decision": "allow_probe", "event": "call_attempt", "failure_rate": 1.0, "probes_in_flight": 1, "reason": "probing_recovery", "state": "half_open", "tool": "db_query", "ts": 216.0, "window_size": 5}
{"consecutive_probe_successes": 0, "event": "outcome", "outcome": "success", "state_after": "closed", "tool": "db_query", "transition": "half_open->closed", "ts": 216.1}
{"decision": "allow", "event": "call_attempt", "failure_rate": 0.0, "reason": "breaker_closed", "state": "closed", "tool": "db_query", "ts": 217.0, "window_size": 0}
```

## What to read from this

- `probe_max_concurrent=1` means only one probe is ever in flight in
  half-open. A probe finishing decrements the counter so the next
  attempt is also allowed; if probes ran in parallel, the second one
  would be denied with `reason=probe_slots_exhausted`.
- `probe_required_successes=2` is the consecutive count. A single
  failure in half-open re-opens the breaker and resets cooldown,
  even if a previous probe in this half-open window succeeded.
- On close, the failure window is **cleared**. The next normal call
  starts from a clean slate — a half-open recovery is a "fresh
  start" verdict, not a "the old failures still count" verdict. This
  is intentional: the alternative is that one stray closed-window
  failure right after recovery re-trips the breaker immediately.

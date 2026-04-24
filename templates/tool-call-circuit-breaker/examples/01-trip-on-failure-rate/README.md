# Example 01 — failure rate trips the breaker, cooldown blocks subsequent calls

## What this shows

The `web_search` tool is called repeatedly. After one success and four
consecutive failures (`window=5, failures=4, rate=0.8`), the failure
rate exceeds the policy threshold of `0.5` and the window has reached
`min_calls=5`. The breaker trips: `closed -> open`. The next two call
attempts (at `ts=105.0` and `ts=110.0`) are denied with
`reason=cooldown_active` because the 30-second cooldown has not yet
elapsed.

## Policy

```json
{
  "window_size": 10,
  "min_calls": 5,
  "failure_rate_threshold": 0.5,
  "cooldown_seconds": 30.0,
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
{"decision": "allow", "event": "call_attempt", "failure_rate": 0.0, "reason": "breaker_closed", "state": "closed", "tool": "web_search", "ts": 100.0, "window_size": 0}
{"event": "outcome", "failure_rate": 0.0, "outcome": "success", "state_after": "closed", "tool": "web_search", "transition": "closed->closed", "ts": 100.1, "window_size": 1}
{"decision": "allow", "event": "call_attempt", "failure_rate": 0.0, "reason": "breaker_closed", "state": "closed", "tool": "web_search", "ts": 101.0, "window_size": 1}
{"event": "outcome", "failure_rate": 0.5, "outcome": "failure", "state_after": "closed", "tool": "web_search", "transition": "closed->closed", "ts": 101.1, "window_size": 2}
{"decision": "allow", "event": "call_attempt", "failure_rate": 0.5, "reason": "breaker_closed", "state": "closed", "tool": "web_search", "ts": 102.0, "window_size": 2}
{"event": "outcome", "failure_rate": 0.667, "outcome": "failure", "state_after": "closed", "tool": "web_search", "transition": "closed->closed", "ts": 102.1, "window_size": 3}
{"decision": "allow", "event": "call_attempt", "failure_rate": 0.667, "reason": "breaker_closed", "state": "closed", "tool": "web_search", "ts": 103.0, "window_size": 3}
{"event": "outcome", "failure_rate": 0.75, "outcome": "failure", "state_after": "closed", "tool": "web_search", "transition": "closed->closed", "ts": 103.1, "window_size": 4}
{"decision": "allow", "event": "call_attempt", "failure_rate": 0.75, "reason": "breaker_closed", "state": "closed", "tool": "web_search", "ts": 104.0, "window_size": 4}
{"event": "outcome", "failure_rate": 0.8, "outcome": "failure", "state_after": "open", "tool": "web_search", "transition": "closed->open", "ts": 104.1, "window_size": 5}
{"cooldown_remaining_s": 29.1, "decision": "denied_open", "event": "call_attempt", "failure_rate": 0.8, "reason": "cooldown_active", "state": "open", "tool": "web_search", "ts": 105.0, "window_size": 5}
{"cooldown_remaining_s": 24.1, "decision": "denied_open", "event": "call_attempt", "failure_rate": 0.8, "reason": "cooldown_active", "state": "open", "tool": "web_search", "ts": 110.0, "window_size": 5}
```

## What to read from this

- The breaker did **not** trip on the second failure (`rate=0.5,
  window=2`) because `window < min_calls=5`. Without `min_calls`, two
  failures in a row would block. That's the "jumpy" anti-pattern.
- The trip happened *exactly* on the call that crossed both gates
  (`window=5, rate=0.8 >= 0.5`).
- After tripping, denied calls do not consume the upstream
  service — the agent should treat `denied_open` as a deterministic
  signal to either pick a fallback tool or surface a structured
  failure to the caller, not as something to retry.

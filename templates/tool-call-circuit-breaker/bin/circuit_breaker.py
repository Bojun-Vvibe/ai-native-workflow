#!/usr/bin/env python3
"""Per-tool circuit breaker for agent tool calls.

States: closed -> open -> half_open -> closed.

- closed: calls pass through; the breaker tracks the last `window_size`
  outcomes. If the failure rate in the window exceeds `failure_rate_threshold`
  AND the window has at least `min_calls` samples, the breaker trips to open.
- open: calls are short-circuited with `denied_open` until `cooldown_seconds`
  elapses since the trip. Then the breaker moves to half_open.
- half_open: at most `probe_max_concurrent` probe calls are allowed through.
  If `probe_required_successes` consecutive probes succeed, the breaker
  closes (and the failure window is reset). If any probe fails, the breaker
  re-trips to open with cooldown reset.

Stdlib only. Deterministic. The clock is injected so tests are reproducible.

CLI:
  circuit_breaker.py demo POLICY.json EVENTS.jsonl
    Replay an event log of {"ts": <unix_seconds>, "tool": "...",
    "outcome": "success"|"failure"|"call_attempt"} lines through the breaker
    and emit one decision JSON per line.
"""

from __future__ import annotations

import json
import sys
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict


@dataclass
class Policy:
    window_size: int
    min_calls: int
    failure_rate_threshold: float
    cooldown_seconds: float
    probe_max_concurrent: int
    probe_required_successes: int


@dataclass
class BreakerState:
    state: str = "closed"  # closed | open | half_open
    window: Deque[str] = field(default_factory=deque)
    opened_at: float = 0.0
    probes_in_flight: int = 0
    consecutive_probe_successes: int = 0


def load_policy(d: dict) -> Policy:
    return Policy(
        window_size=int(d["window_size"]),
        min_calls=int(d["min_calls"]),
        failure_rate_threshold=float(d["failure_rate_threshold"]),
        cooldown_seconds=float(d["cooldown_seconds"]),
        probe_max_concurrent=int(d["probe_max_concurrent"]),
        probe_required_successes=int(d["probe_required_successes"]),
    )


def _failure_rate(window: Deque[str]) -> float:
    if not window:
        return 0.0
    fails = sum(1 for x in window if x == "failure")
    return fails / len(window)


def decide(policy: Policy, st: BreakerState, now: float, tool: str) -> dict:
    """Decide whether a new call attempt is allowed.

    Returns dict with: decision (allow|allow_probe|denied_open),
    state, reason, failure_rate, window_size.
    """
    # Maybe transition open -> half_open
    if st.state == "open" and now - st.opened_at >= policy.cooldown_seconds:
        st.state = "half_open"
        st.probes_in_flight = 0
        st.consecutive_probe_successes = 0

    if st.state == "open":
        return {
            "decision": "denied_open",
            "state": "open",
            "tool": tool,
            "reason": "cooldown_active",
            "cooldown_remaining_s": round(
                policy.cooldown_seconds - (now - st.opened_at), 3
            ),
            "failure_rate": round(_failure_rate(st.window), 3),
            "window_size": len(st.window),
        }

    if st.state == "half_open":
        if st.probes_in_flight >= policy.probe_max_concurrent:
            return {
                "decision": "denied_open",
                "state": "half_open",
                "tool": tool,
                "reason": "probe_slots_exhausted",
                "probes_in_flight": st.probes_in_flight,
                "failure_rate": round(_failure_rate(st.window), 3),
                "window_size": len(st.window),
            }
        st.probes_in_flight += 1
        return {
            "decision": "allow_probe",
            "state": "half_open",
            "tool": tool,
            "reason": "probing_recovery",
            "probes_in_flight": st.probes_in_flight,
            "failure_rate": round(_failure_rate(st.window), 3),
            "window_size": len(st.window),
        }

    # closed
    return {
        "decision": "allow",
        "state": "closed",
        "tool": tool,
        "reason": "breaker_closed",
        "failure_rate": round(_failure_rate(st.window), 3),
        "window_size": len(st.window),
    }


def record(policy: Policy, st: BreakerState, now: float, outcome: str) -> dict:
    """Record the outcome of a call. Updates window and state.

    outcome must be "success" or "failure".
    Returns a state-transition record.
    """
    if outcome not in ("success", "failure"):
        raise ValueError(f"outcome must be success|failure, got {outcome!r}")

    prev = st.state

    if st.state == "half_open":
        st.probes_in_flight = max(0, st.probes_in_flight - 1)
        if outcome == "success":
            st.consecutive_probe_successes += 1
            if st.consecutive_probe_successes >= policy.probe_required_successes:
                st.state = "closed"
                st.window.clear()
                st.consecutive_probe_successes = 0
        else:
            # Any probe failure re-opens the breaker, cooldown resets.
            st.state = "open"
            st.opened_at = now
            st.consecutive_probe_successes = 0
        return {
            "transition": f"{prev}->{st.state}",
            "outcome": outcome,
            "consecutive_probe_successes": st.consecutive_probe_successes,
        }

    # closed: append to window and check threshold
    st.window.append(outcome)
    while len(st.window) > policy.window_size:
        st.window.popleft()
    fr = _failure_rate(st.window)
    if (
        st.state == "closed"
        and len(st.window) >= policy.min_calls
        and fr >= policy.failure_rate_threshold
    ):
        st.state = "open"
        st.opened_at = now
        return {
            "transition": "closed->open",
            "outcome": outcome,
            "failure_rate": round(fr, 3),
            "window_size": len(st.window),
        }
    return {
        "transition": "closed->closed",
        "outcome": outcome,
        "failure_rate": round(fr, 3),
        "window_size": len(st.window),
    }


def _demo(policy_path: str, events_path: str) -> int:
    with open(policy_path) as f:
        policy_data = json.load(f)
    policy = load_policy(policy_data)

    states: Dict[str, BreakerState] = {}

    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            tool = ev["tool"]
            ts = float(ev["ts"])
            kind = ev["event"]
            st = states.setdefault(tool, BreakerState())
            if kind == "call_attempt":
                d = decide(policy, st, ts, tool)
                d["ts"] = ts
                d["event"] = "call_attempt"
                print(json.dumps(d, sort_keys=True))
            elif kind in ("success", "failure"):
                r = record(policy, st, ts, kind)
                r["ts"] = ts
                r["tool"] = tool
                r["event"] = "outcome"
                r["state_after"] = st.state
                print(json.dumps(r, sort_keys=True))
            else:
                raise ValueError(f"unknown event kind: {kind!r}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "demo":
        return _demo(argv[2], argv[3])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

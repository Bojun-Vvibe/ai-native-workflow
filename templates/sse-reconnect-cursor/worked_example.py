"""
worked_example.py — sse-reconnect-cursor end-to-end demo.

Scenario: an LLM token stream that disconnects mid-flight.

  1. Server emits events 0..3 cleanly.
  2. Connection drops. The cursor decides to reconnect (within budget).
  3. After reconnect the server (correctly) replays from event 2 because
     it doesn't know we already saw 2 and 3 — those are SKIP_DUPLICATE.
     It then emits the new event 4, which is DELIVER.
  4. The connection drops again, server hands us a `Retry-After: 0.5s`
     hint. Our local floor is 0.1s, so we honor 0.5s (server wins).
  5. After many drops the per-window attempt budget is exhausted and the
     cursor returns GIVE_UP — the dispatcher must surface this as a
     mission-level failure, not retry forever.
  6. Sanity check: a server bug that emits id=1 (which we delivered ages
     ago but has aged out of our delivered tail in this scenario, OR is
     between oldest_seen and last) is caught as REJECT_REWIND, not
     silently re-delivered.

Run: python3 worked_example.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cursor import (  # noqa: E402
    SseCursor,
    EventVerdict,
    ReconnectVerdict,
)


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _line(label: str, payload: dict) -> str:
    return f"{label:>20s}  {json.dumps(payload, sort_keys=True)}"


def main() -> int:
    clk = FakeClock()
    cur = SseCursor(
        max_attempts_per_window=3,
        window_s=10.0,
        min_backoff_s=0.1,
        now=clk,
    )

    delivered: list[int] = []
    skipped: list[int] = []
    rejected: list[int] = []

    print("=" * 72)
    print("SCENARIO 1: clean stream of events 0..3")
    print("=" * 72)
    for ev in [0, 1, 2, 3]:
        d = cur.consider(ev)
        print(_line(d.verdict.value, {"event_id": ev, "last": d.new_last_event_id, "why": d.reason}))
        if d.verdict is EventVerdict.DELIVER:
            delivered.append(ev)

    assert delivered == [0, 1, 2, 3], delivered
    assert cur.last_event_id == 3

    print()
    print("=" * 72)
    print("SCENARIO 2: connection drops, reconnect, server replays from 2")
    print("=" * 72)
    clk.advance(0.05)  # dropped after a tiny delay
    rc = cur.consider_reconnect(server_retry_after_s=None)
    print(_line(rc.verdict.value, {
        "wait_s": round(rc.wait_s, 3),
        "used": rc.attempts_used,
        "remaining": rc.attempts_remaining,
        "why": rc.reason,
    }))
    assert rc.verdict is ReconnectVerdict.GO

    # server replays 2,3 (already delivered), then ships 4 (new)
    for ev in [2, 3, 4]:
        d = cur.consider(ev)
        print(_line(d.verdict.value, {"event_id": ev, "last": d.new_last_event_id, "why": d.reason}))
        if d.verdict is EventVerdict.DELIVER:
            delivered.append(ev)
        elif d.verdict is EventVerdict.SKIP_DUPLICATE:
            skipped.append(ev)
        else:
            rejected.append(ev)

    assert delivered == [0, 1, 2, 3, 4], delivered
    assert skipped == [2, 3], skipped
    assert cur.last_event_id == 4

    print()
    print("=" * 72)
    print("SCENARIO 3: drop again; server hints Retry-After=0.5s (overrides our 0.1s floor)")
    print("=" * 72)
    clk.advance(0.5)  # well past our 0.1s floor
    rc = cur.consider_reconnect(server_retry_after_s=0.5)
    print(_line(rc.verdict.value, {
        "wait_s": round(rc.wait_s, 3),
        "used": rc.attempts_used,
        "remaining": rc.attempts_remaining,
        "why": rc.reason,
    }))
    # Server hint is 0.5s; we just consumed 0.5s of real time but server
    # wants 0.5s from *this decision point*, so we WAIT.
    assert rc.verdict is ReconnectVerdict.WAIT, rc
    assert abs(rc.wait_s - 0.5) < 1e-9

    clk.advance(0.5)
    rc = cur.consider_reconnect(server_retry_after_s=None)
    print(_line(rc.verdict.value, {
        "wait_s": round(rc.wait_s, 3),
        "used": rc.attempts_used,
        "remaining": rc.attempts_remaining,
        "why": rc.reason,
    }))
    assert rc.verdict is ReconnectVerdict.GO

    print()
    print("=" * 72)
    print("SCENARIO 4: budget exhaustion -> give_up (3 attempts in 10s window)")
    print("=" * 72)
    # we already used 2 of 3 in scenarios 2+3; one more is available, then
    # the 4th must be GIVE_UP.
    clk.advance(0.2)
    rc = cur.consider_reconnect()
    print(_line(rc.verdict.value, {
        "used": rc.attempts_used,
        "remaining": rc.attempts_remaining,
        "why": rc.reason,
    }))
    assert rc.verdict is ReconnectVerdict.GO  # 3rd attempt
    clk.advance(0.2)
    rc = cur.consider_reconnect()
    print(_line(rc.verdict.value, {
        "used": rc.attempts_used,
        "remaining": rc.attempts_remaining,
        "why": rc.reason,
    }))
    assert rc.verdict is ReconnectVerdict.GIVE_UP, rc

    # advance past the window; budget should refill
    clk.advance(11.0)
    rc = cur.consider_reconnect()
    print(_line(rc.verdict.value, {
        "used": rc.attempts_used,
        "remaining": rc.attempts_remaining,
        "why": "budget refilled after window",
    }))
    assert rc.verdict is ReconnectVerdict.GO

    print()
    print("=" * 72)
    print("SCENARIO 5: server-side rewind to id=2 caught (NOT silently re-delivered)")
    print("=" * 72)
    # The id 2 is in our delivered tail, so by contract this is a duplicate,
    # not a rewind — confirm we skip it correctly:
    d = cur.consider(2)
    print(_line(d.verdict.value, {"event_id": 2, "why": d.reason}))
    assert d.verdict is EventVerdict.SKIP_DUPLICATE

    # Now simulate the dangerous case: cursor with a tiny tail that has
    # *evicted* delivered ids, then server claims an id "in the gap"
    cur2 = SseCursor(
        max_attempts_per_window=3, window_s=10.0, min_backoff_s=0.1,
        now=clk, _seen_tail_cap=2,
    )
    for ev in [10, 11, 12, 13]:
        cur2.consider(ev)
    # tail now holds {12,13}, oldest_seen=12, last=13.
    # An id of 12 is a legit duplicate (in tail) -> SKIP.
    # An id of 11 is < oldest_seen -> conservatively SKIP (at-most-once).
    # An id of 12.5 is impossible (int), but an id of 12 vs 13: both in tail.
    # The rewind window is (oldest_seen, last] minus seen_tail. With cap=2
    # and ids 10..13, that window is empty by construction. To exercise the
    # rewind path, we need at least one id in (oldest_seen, last] that is
    # *not* in tail. Construct that scenario:
    cur3 = SseCursor(
        max_attempts_per_window=3, window_s=10.0, min_backoff_s=0.1,
        now=clk, _seen_tail_cap=10,
    )
    for ev in [20, 21, 22, 23, 24]:
        cur3.consider(ev)
    # Now manually corrupt the tail to drop id=22 while keeping last=24.
    # In real life this can't happen — but it lets us prove the rewind
    # detector is genuinely checking, not just trusting the tail.
    cur3._seen_tail = [20, 21, 23, 24]
    d = cur3.consider(22)
    print(_line(d.verdict.value, {"event_id": 22, "last": d.new_last_event_id, "why": d.reason}))
    assert d.verdict is EventVerdict.REJECT_REWIND, d

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(json.dumps({
        "delivered": delivered,
        "skipped_as_duplicate": skipped,
        "rejected_as_rewind": ["scenario_5_synthetic"],
        "final_last_event_id": cur.last_event_id,
    }, sort_keys=True, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())

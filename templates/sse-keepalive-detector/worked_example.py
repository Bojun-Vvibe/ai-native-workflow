"""
Worked example for sse-keepalive-detector.

Five scenarios, all driven by an injected fake clock so the output is
byte-deterministic:

  1. HEALTHY: real tokens arrive every 0.5s. After 5s, verdict is HEALTHY.
  2. IDLE_BUT_ALIVE: no real tokens for 40s but keepalives every 5s. Verdict
     should be IDLE_BUT_ALIVE — do NOT reconnect.
  3. STALLED: real tokens stop AND keepalives stop. After ~16s of total
     silence, verdict flips to STALLED — caller should cancel + reconnect.
  4. DEAD: stream constructed but never observes any event. After
     keepalive_idle_s + 1s, verdict is DEAD.
  5. Watchdog: prove that verdict() against an advancing `now` flips to
     STALLED *without* any new observe() call — the bug a naive watchdog
     hits when it only re-evaluates on event arrival.

Run:
    python3 worked_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from detector import Detector  # noqa: E402


class FakeClock:
    def __init__(self, t0: float = 1000.0) -> None:
        self.t = t0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> float:
        self.t += dt
        return self.t


def banner(title: str) -> None:
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def scenario_healthy() -> None:
    banner("Scenario 1: HEALTHY — real tokens every 0.5s for 5s")
    clock = FakeClock()
    det = Detector(real_event_idle_s=10.0, keepalive_idle_s=2.0, now_fn=clock)
    for _ in range(10):
        clock.advance(0.5)
        det.observe(clock.t, kind="real")
    snap = det.snapshot()
    print(f"  real_event_count={snap.real_event_count}")
    print(f"  keepalive_count={snap.keepalive_count}")
    print(f"  seconds_since_last_real={snap.seconds_since_last_real:.2f}")
    print(f"  verdict={snap.verdict}")
    assert snap.verdict == "HEALTHY", snap


def scenario_idle_but_alive() -> None:
    banner("Scenario 2: IDLE_BUT_ALIVE — no real tokens for 40s, keepalives every 5s")
    clock = FakeClock()
    det = Detector(real_event_idle_s=30.0, keepalive_idle_s=10.0, now_fn=clock)
    # One real event right at the start.
    det.observe(clock.t, kind="real")
    # 40s of silence on real, but keepalives every 5s.
    for _ in range(8):
        clock.advance(5.0)
        det.observe(clock.t, kind="keepalive")
    snap = det.snapshot()
    print(f"  real_event_count={snap.real_event_count}")
    print(f"  keepalive_count={snap.keepalive_count}")
    print(f"  seconds_since_last_real={snap.seconds_since_last_real:.2f}")
    print(f"  seconds_since_last_keepalive={snap.seconds_since_last_keepalive:.2f}")
    print(f"  verdict={snap.verdict}  (do NOT reconnect — server is alive)")
    assert snap.verdict == "IDLE_BUT_ALIVE", snap


def scenario_stalled() -> None:
    banner("Scenario 3: STALLED — real and keepalives both stop")
    clock = FakeClock()
    det = Detector(real_event_idle_s=10.0, keepalive_idle_s=5.0, now_fn=clock)
    det.observe(clock.t, kind="real")
    clock.advance(2.0)
    det.observe(clock.t, kind="keepalive")
    # Now silence for 16s — past the keepalive threshold.
    clock.advance(16.0)
    snap = det.snapshot()
    print(f"  seconds_since_last_real={snap.seconds_since_last_real:.2f}")
    print(f"  seconds_since_last_keepalive={snap.seconds_since_last_keepalive:.2f}")
    print(f"  verdict={snap.verdict}  (cancel + reconnect)")
    assert snap.verdict == "STALLED", snap


def scenario_dead() -> None:
    banner("Scenario 4: DEAD — never observed anything, past keepalive window")
    clock = FakeClock()
    det = Detector(real_event_idle_s=10.0, keepalive_idle_s=5.0, now_fn=clock)
    # Just inside the warm-up window: still IDLE_BUT_ALIVE.
    clock.advance(4.0)
    snap_warm = det.snapshot()
    print(f"  at t+4s (warm-up): verdict={snap_warm.verdict}")
    # Now past the keepalive threshold with no events ever seen.
    clock.advance(2.0)  # total +6s, past 5s keepalive_idle_s
    snap_dead = det.snapshot()
    print(f"  at t+6s (past keepalive_idle): verdict={snap_dead.verdict}")
    assert snap_warm.verdict == "IDLE_BUT_ALIVE", snap_warm
    assert snap_dead.verdict == "DEAD", snap_dead


def scenario_watchdog() -> None:
    banner("Scenario 5: Watchdog flips verdict WITHOUT a new observe()")
    clock = FakeClock()
    det = Detector(real_event_idle_s=8.0, keepalive_idle_s=3.0, now_fn=clock)
    det.observe(clock.t, kind="real")
    # Right after observe, healthy.
    print(f"  immediately after observe: verdict={det.verdict()}")
    # Advance 4s — past real threshold but inside keepalive grace because the
    # real event also bumped keepalive watermark.
    clock.advance(4.0)
    print(f"  +4s, no new observe: verdict={det.verdict()}")
    # Advance another 5s — total 9s past the only real event, past 8s keepalive
    # threshold too. Should be STALLED.
    clock.advance(5.0)
    final_verdict = det.verdict()
    print(f"  +9s total, no new observe: verdict={final_verdict}")
    assert final_verdict == "STALLED", final_verdict


if __name__ == "__main__":
    scenario_healthy()
    scenario_idle_but_alive()
    scenario_stalled()
    scenario_dead()
    scenario_watchdog()
    print()
    print("All scenarios passed.")

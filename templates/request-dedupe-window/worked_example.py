"""Worked example: sliding-window request deduplication.

Four scenarios:
  1. Burst of identical submits inside the window -> first forwards,
     rest are suppressed with monotonically increasing suppressed_count.
  2. After the window elapses, the same key is forwarded again
     (window resets; counts go back to zero).
  3. Different requests yield different keys and never collide.
  4. sweep() evicts stale entries; active_keys() reflects only the live set.

Uses an injected clock so output is fully deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from template import RequestDedupeWindow  # noqa: E402


class FakeClock:
    """Deterministic clock; advance with .tick(seconds)."""

    def __init__(self, t0: float = 1000.0) -> None:
        self.t = t0

    def __call__(self) -> float:
        return self.t

    def tick(self, dt: float) -> None:
        self.t += dt


def request_key(req):
    # Trivial canonicalizer: (method, path). Real callers should canonicalize
    # query args, sort headers, etc. — that's out of scope for this template.
    return f"{req['method']}:{req['path']}"


def case_burst_inside_window():
    print("=== burst inside window: first forwards, rest suppress ===")
    clk = FakeClock()
    dq = RequestDedupeWindow(window_seconds=5.0, key_fn=request_key, now_fn=clk)
    req = {"method": "POST", "path": "/v1/charge"}
    for i in range(4):
        d = dq.submit(req)
        print(
            f"  t={clk.t:>7.2f}  verdict={d.verdict:<8} "
            f"age_s={d.age_s:5.2f}  suppressed_count={d.suppressed_count}"
        )
        clk.tick(0.5)
    stats = dq.stats()
    print(f"  stats: {stats}")
    assert stats["total_suppressed"] == 3
    assert stats["active_keys_live"] == 1
    print()


def case_window_elapses_resets():
    print("=== window elapses -> same key forwards again, counts reset ===")
    clk = FakeClock()
    dq = RequestDedupeWindow(window_seconds=2.0, key_fn=request_key, now_fn=clk)
    req = {"method": "GET", "path": "/v1/status"}
    d1 = dq.submit(req)
    print(f"  t={clk.t:>7.2f}  {d1.verdict}  suppressed_count={d1.suppressed_count}")
    clk.tick(0.5)
    d2 = dq.submit(req)
    print(f"  t={clk.t:>7.2f}  {d2.verdict}  age_s={d2.age_s:.2f}  suppressed_count={d2.suppressed_count}")
    clk.tick(2.0)  # total elapsed since first = 2.5s, > window 2.0s
    d3 = dq.submit(req)
    print(f"  t={clk.t:>7.2f}  {d3.verdict}  age_s={d3.age_s:.2f}  suppressed_count={d3.suppressed_count}")
    assert d1.verdict == "forward"
    assert d2.verdict == "suppress" and d2.suppressed_count == 1
    assert d3.verdict == "forward" and d3.suppressed_count == 0
    print()


def case_distinct_keys_no_collision():
    print("=== distinct requests get distinct keys ===")
    clk = FakeClock()
    dq = RequestDedupeWindow(window_seconds=10.0, key_fn=request_key, now_fn=clk)
    reqs = [
        {"method": "POST", "path": "/v1/charge"},
        {"method": "POST", "path": "/v1/refund"},
        {"method": "GET", "path": "/v1/status"},
        {"method": "POST", "path": "/v1/charge"},   # duplicate of first
    ]
    for r in reqs:
        d = dq.submit(r)
        print(f"  {r['method']} {r['path']:<14} -> {d.verdict}  key={d.key}")
    stats = dq.stats()
    print(f"  stats: {stats}")
    assert stats["active_keys_live"] == 3   # three distinct keys
    assert stats["total_suppressed"] == 1   # the second /v1/charge
    print()


def case_sweep_evicts_stale():
    print("=== sweep() evicts stale entries ===")
    clk = FakeClock()
    dq = RequestDedupeWindow(window_seconds=1.0, key_fn=request_key, now_fn=clk)
    dq.submit({"method": "GET", "path": "/a"})
    dq.submit({"method": "GET", "path": "/b"})
    print(f"  before tick: active_keys={dq.active_keys()}")
    clk.tick(2.0)
    dq.submit({"method": "GET", "path": "/c"})       # fresh entry
    print(f"  after  tick + new key: active_keys (lazy) = {dq.active_keys()}")
    evicted = dq.sweep()
    print(f"  sweep() evicted {evicted}; active_keys = {dq.active_keys()}")
    assert evicted == 2
    assert dq.active_keys() == 1
    print()


def main() -> int:
    case_burst_inside_window()
    case_window_elapses_resets()
    case_distinct_keys_no_collision()
    case_sweep_evicts_stale()
    print("all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

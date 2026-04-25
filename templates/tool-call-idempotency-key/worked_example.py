"""Worked example: idempotency-keyed wrapper around a non-idempotent tool."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from template import (  # noqa: E402
    IdempotencyCache,
    IdempotencyKeyConflict,
    IdempotencyKeyInFlight,
    with_idempotency,
)


# Simulated controllable clock so the worked example is deterministic.
class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# Pretend tool: counts every real invocation. Not idempotent on its own —
# every call would create a new ticket.
class TicketTool:
    def __init__(self) -> None:
        self.calls = 0

    def create_ticket(self, title: str, priority: str = "p2") -> dict:
        self.calls += 1
        return {"ticket_id": f"T-{self.calls:04d}", "title": title, "priority": priority}


def main() -> int:
    clk = FakeClock()
    cache = IdempotencyCache(ttl_seconds=60.0, clock=clk)
    tool = TicketTool()
    create = with_idempotency(cache, tool.create_ticket)

    print("=== first call (miss) ===")
    r1 = create("disk full on host-7", priority="p1", idempotency_key="op-abc")
    print(f"  result={r1}  underlying_calls={tool.calls}")

    print("=== retry within TTL, same key + args (hit, replay) ===")
    r2 = create("disk full on host-7", priority="p1", idempotency_key="op-abc")
    print(f"  result={r2}  underlying_calls={tool.calls}")
    assert r1 == r2
    assert tool.calls == 1

    print("=== different key, same args (miss, fires again) ===")
    r3 = create("disk full on host-7", priority="p1", idempotency_key="op-xyz")
    print(f"  result={r3}  underlying_calls={tool.calls}")
    assert r3["ticket_id"] != r1["ticket_id"]
    assert tool.calls == 2

    print("=== same key, different args (conflict raised) ===")
    try:
        create("disk full on host-7", priority="p3", idempotency_key="op-abc")
    except IdempotencyKeyConflict as e:
        print(f"  raised: {e}")
    else:
        print("  ERROR: expected conflict")
        return 1
    assert tool.calls == 2  # tool not invoked

    print("=== TTL expiry: same key fires fresh after window ===")
    clk.advance(120.0)
    r4 = create("disk full on host-7", priority="p1", idempotency_key="op-abc")
    print(f"  result={r4}  underlying_calls={tool.calls}")
    assert tool.calls == 3
    assert r4["ticket_id"] != r1["ticket_id"]

    print("=== in-flight detection ===")
    in_flight_cache = IdempotencyCache(ttl_seconds=60.0, clock=clk)
    seen_in_flight = []

    def slow_tool(x: int) -> int:
        # Simulate a duplicate arriving while we are still running.
        status, _ = in_flight_cache.get("k1", _hash_args((x,), {}))
        seen_in_flight.append(status)
        return x * 10

    wrapped = with_idempotency(in_flight_cache, slow_tool)
    out = wrapped(7, idempotency_key="k1")
    print(f"  out={out}  status_seen_during_call={seen_in_flight}")
    assert out == 70
    assert seen_in_flight == ["in_flight"]

    # And the post-completion duplicate now hits the cache instead of in-flight.
    out2 = wrapped(7, idempotency_key="k1")
    assert out2 == 70

    # Explicit in-flight raise demonstration: simulate by manually reserving.
    in_flight_cache.reserve("k2", "deadbeef")
    try:
        wrapped(0, idempotency_key="k2")  # args_hash for () != "deadbeef" -> conflict
    except IdempotencyKeyConflict as e:
        print(f"  reserved-with-other-args -> conflict: {e}")
    in_flight_cache.reserve("k3", _hash_args((1,), {}))
    try:
        wrapped(1, idempotency_key="k3")
    except IdempotencyKeyInFlight as e:
        print(f"  reserved-same-args -> in-flight: {e}")

    print("all assertions passed")
    return 0


def _hash_args(args, kwargs):
    # Reach into the template's helper indirectly to keep the demo self-contained.
    from template import _canonical_args_hash
    return _canonical_args_hash(args, kwargs)


if __name__ == "__main__":
    raise SystemExit(main())

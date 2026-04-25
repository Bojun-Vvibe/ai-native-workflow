"""Worked example for tool-call-rate-limit-backpressure.

Four parts, all stdlib, all deterministic via injected clock:

  1. Burst absorbs short spikes — burst=5 lets 5 immediate submits
     through; the 6th is Throttled with a precise retry_after_s.
  2. Queue fills, the limiter starts Rejecting (load shedding).
  3. complete() frees a slot AND the bucket refills with time —
     Throttled becomes Admitted again at the right moment.
  4. UnknownTicket: complete() with a bad id raises loudly.
"""

from __future__ import annotations

from limiter import (
    Admitted,
    RateLimitBackpressure,
    Rejected,
    Throttled,
    UnknownTicket,
)


class FakeClock:
    def __init__(self, t0: float = 1000.0) -> None:
        self.t = t0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def part_1_burst_then_throttle() -> None:
    section("Part 1: burst absorbs spike, surplus is Throttled (not silently queued)")
    clock = FakeClock()
    lim = RateLimitBackpressure(
        rate_per_sec=2.0, burst=5, queue_capacity=10, now_fn=clock
    )
    verdicts = [lim.submit() for _ in range(7)]
    for i, v in enumerate(verdicts):
        kind = type(v).__name__
        extra = ""
        if isinstance(v, Admitted):
            extra = f" ticket={v.ticket_id} depth_after={v.queue_depth_after}"
        elif isinstance(v, Throttled):
            extra = f" retry_after_s={v.retry_after_s:.3f} depth={v.queue_depth}"
        print(f"  submit #{i+1}: {kind}{extra}")
    assert sum(isinstance(v, Admitted) for v in verdicts) == 5
    assert sum(isinstance(v, Throttled) for v in verdicts) == 2
    # retry_after is 0.5s for first throttled (1 token deficit / 2 per sec)
    first_throttled = next(v for v in verdicts if isinstance(v, Throttled))
    assert abs(first_throttled.retry_after_s - 0.5) < 1e-9
    print(f"counters: admitted={lim.admitted_count} throttled={lim.throttled_count}")


def part_2_queue_fills_then_rejects() -> None:
    section("Part 2: queue fills, surplus is Rejected (load shed signal)")
    clock = FakeClock()
    # Big burst, tiny queue, so we can observe Rejected without
    # racing the bucket.
    lim = RateLimitBackpressure(
        rate_per_sec=100.0, burst=10, queue_capacity=3, now_fn=clock
    )
    verdicts = [lim.submit() for _ in range(6)]
    for i, v in enumerate(verdicts):
        kind = type(v).__name__
        extra = ""
        if isinstance(v, Admitted):
            extra = f" ticket={v.ticket_id} depth_after={v.queue_depth_after}"
        elif isinstance(v, Rejected):
            extra = f" depth={v.queue_depth}/{v.queue_capacity}"
        print(f"  submit #{i+1}: {kind}{extra}")
    admitted = [v for v in verdicts if isinstance(v, Admitted)]
    rejected = [v for v in verdicts if isinstance(v, Rejected)]
    assert len(admitted) == 3, admitted
    assert len(rejected) == 3, rejected
    assert all(r.queue_depth == 3 and r.queue_capacity == 3 for r in rejected)
    print(f"counters: admitted={lim.admitted_count} rejected={lim.rejected_count}")


def part_3_complete_and_refill_unblock() -> None:
    section("Part 3: complete() frees slot + clock advance refills bucket")
    clock = FakeClock()
    lim = RateLimitBackpressure(
        rate_per_sec=2.0, burst=2, queue_capacity=2, now_fn=clock
    )
    a1 = lim.submit()
    a2 = lim.submit()
    assert isinstance(a1, Admitted) and isinstance(a2, Admitted)
    # Bucket and queue both at limit. Next submit must be Throttled
    # (queue still has capacity 2 used by 2 calls — actually full, so Rejected).
    v3 = lim.submit()
    print(f"  submit #3 (queue full): {type(v3).__name__}")
    assert isinstance(v3, Rejected)

    # Complete one call — slot frees but bucket is still empty
    # (no time has passed). So next submit is Throttled, not Admitted.
    lim.complete(a1.ticket_id)
    v4 = lim.submit()
    print(
        f"  submit #4 (slot freed, bucket empty): "
        f"{type(v4).__name__}"
        + (
            f" retry_after_s={v4.retry_after_s:.3f}"
            if isinstance(v4, Throttled)
            else ""
        )
    )
    assert isinstance(v4, Throttled)
    assert abs(v4.retry_after_s - 0.5) < 1e-9

    # Advance time by exactly retry_after; now we should be admitted.
    clock.advance(v4.retry_after_s)
    v5 = lim.submit()
    print(
        f"  submit #5 (after {v4.retry_after_s:.3f}s wait): "
        f"{type(v5).__name__}"
        + (f" ticket={v5.ticket_id}" if isinstance(v5, Admitted) else "")
    )
    assert isinstance(v5, Admitted)
    print(
        f"counters: admitted={lim.admitted_count} "
        f"throttled={lim.throttled_count} rejected={lim.rejected_count} "
        f"completed={lim.completed_count}"
    )


def part_4_unknown_ticket_raises() -> None:
    section("Part 4: complete(bad_ticket) raises UnknownTicket")
    lim = RateLimitBackpressure(rate_per_sec=1.0, burst=1, queue_capacity=1)
    a = lim.submit()
    assert isinstance(a, Admitted)
    lim.complete(a.ticket_id)
    try:
        lim.complete(a.ticket_id)  # double-complete
    except UnknownTicket as exc:
        print(f"  double-complete raised: {exc}")
    try:
        lim.complete(99999)
    except UnknownTicket as exc:
        print(f"  bogus ticket raised: {exc}")


def main() -> None:
    part_1_burst_then_throttle()
    part_2_queue_fills_then_rejects()
    part_3_complete_and_refill_unblock()
    part_4_unknown_ticket_raises()
    print("\nAll 4 parts OK.")


if __name__ == "__main__":
    main()

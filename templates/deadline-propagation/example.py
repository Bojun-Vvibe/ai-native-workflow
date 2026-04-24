"""Worked example: a 3-level nested agent call chain with deadline propagation.

  orchestrator (budget=500ms, reserve=50ms)
    -> planner    (gets 450ms, reserve=30ms)
       -> tool_a  (gets 420ms)        # fast, returns
       -> tool_b  (gets remaining)    # slow, exceeds -> caught, partial returned
    -> finalize_partial               # runs inside the 50ms reserve

Uses an injected fake clock so output is byte-stable.
"""

from __future__ import annotations

from deadline import Deadline, DeadlineExceeded, with_deadline


class FakeClock:
    """Monotonic clock that only advances when we tell it to."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms / 1000.0


def tool_a(deadline: Deadline, clock: FakeClock) -> str:
    deadline = with_deadline(deadline, "tool_a")
    print(f"  tool_a: start, remaining={deadline.remaining_ms()}ms")
    clock.advance_ms(80)  # tool_a takes 80ms
    print(f"  tool_a: done,  remaining={deadline.remaining_ms()}ms")
    return "A_RESULT"


def tool_b(deadline: Deadline, clock: FakeClock) -> str:
    deadline = with_deadline(deadline, "tool_b")
    print(f"  tool_b: start, remaining={deadline.remaining_ms()}ms")
    # Simulate a slow upstream that would take 600ms; check deadline mid-flight.
    for step in range(6):
        clock.advance_ms(100)
        try:
            deadline.check(f"tool_b step {step}")
        except DeadlineExceeded as e:
            print(f"  tool_b: aborted at step {step} ({e})")
            raise
    return "B_RESULT"


def planner(deadline: Deadline, clock: FakeClock) -> dict:
    deadline = with_deadline(deadline, "planner")
    print(f"planner: start, remaining={deadline.remaining_ms()}ms")
    results: dict = {"a": None, "b": None, "errors": []}

    # Each child gets a deadline shrunk by planner's own reserve.
    a_deadline = deadline.child(reserve_ms=30)
    try:
        results["a"] = tool_a(a_deadline, clock)
    except DeadlineExceeded as e:
        results["errors"].append(f"tool_a: {e}")

    b_deadline = deadline.child(reserve_ms=30)
    try:
        results["b"] = tool_b(b_deadline, clock)
    except DeadlineExceeded as e:
        results["errors"].append(f"tool_b: {e}")

    print(f"planner: done,  remaining={deadline.remaining_ms()}ms")
    return results


def orchestrator(budget_ms: int, clock: FakeClock) -> dict:
    deadline = Deadline.in_ms(budget_ms, clock=clock)
    print(f"orchestrator: budget={budget_ms}ms")

    # Planner gets the orchestrator's deadline minus 50ms reserved for finalize.
    planner_deadline = deadline.child(reserve_ms=50)

    try:
        partial = planner(planner_deadline, clock)
        outcome = "ok" if not partial["errors"] else "partial"
    except DeadlineExceeded as e:
        partial = {"errors": [f"planner: {e}"]}
        outcome = "deadline_exceeded"

    # The 50ms reserve guarantees we still have time to assemble & return.
    print(
        f"orchestrator: outcome={outcome}, "
        f"reserve_remaining={deadline.remaining_ms()}ms"
    )
    return {"outcome": outcome, "result": partial}


if __name__ == "__main__":
    clock = FakeClock(start=1000.0)
    envelope = orchestrator(budget_ms=500, clock=clock)
    print()
    print("FINAL ENVELOPE:")
    for k, v in envelope.items():
        print(f"  {k}: {v}")

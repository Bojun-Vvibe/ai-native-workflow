"""Deadline propagation primitive for nested agent/tool calls.

A single absolute deadline (monotonic seconds) is threaded through every
sub-call. Each child reserves a small `reserve_ms` slack for its own cleanup
(emit partial result, flush trace, return envelope) and shrinks the deadline
it passes downstream by that reserve. When `remaining_ms()` <= 0 a
`DeadlineExceeded` is raised *before* the next outbound call, so the agent
never burns budget on a request whose response it cannot use.

Stdlib only. Clock is injectable for deterministic tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional


class DeadlineExceeded(Exception):
    """Raised when the caller-supplied deadline has passed."""


Clock = Callable[[], float]


def _default_clock() -> float:
    return time.monotonic()


@dataclass(frozen=True)
class Deadline:
    """Absolute deadline in monotonic seconds.

    Use `Deadline.in_ms(budget_ms)` at the entry point. Pass the result down.
    Children call `.child(reserve_ms=...)` before invoking grand-children.
    """

    expires_at: float
    clock: Clock = _default_clock

    @classmethod
    def in_ms(cls, budget_ms: int, clock: Clock = _default_clock) -> "Deadline":
        if budget_ms < 0:
            raise ValueError("budget_ms must be >= 0")
        return cls(expires_at=clock() + budget_ms / 1000.0, clock=clock)

    def remaining_ms(self) -> int:
        return max(0, int((self.expires_at - self.clock()) * 1000))

    def expired(self) -> bool:
        return self.clock() >= self.expires_at

    def check(self, op: str = "operation") -> None:
        """Raise DeadlineExceeded if deadline already passed."""
        if self.expired():
            raise DeadlineExceeded(f"deadline exceeded before {op}")

    def child(self, reserve_ms: int = 50) -> "Deadline":
        """Derive a child deadline that ends `reserve_ms` earlier.

        The reserve is the budget the *current* frame keeps for itself
        (emit partial result, log, return). Children never see it.
        """
        if reserve_ms < 0:
            raise ValueError("reserve_ms must be >= 0")
        new_expires = self.expires_at - reserve_ms / 1000.0
        # Floor at "now" so we never produce a deadline in the past silently;
        # the child's first .check() will then raise immediately.
        return Deadline(expires_at=max(new_expires, self.clock()), clock=self.clock)


def with_deadline(deadline: Optional[Deadline], op: str = "operation") -> Deadline:
    """Defensive entry guard: accept Optional, reject expired, return non-None."""
    if deadline is None:
        raise ValueError(f"{op}: deadline is required (no implicit infinity)")
    deadline.check(op)
    return deadline

"""Step-budget monitor for agent loops with phase allocation and soft warnings.

Why this exists
---------------
``agent-loop-iteration-cap`` is a single hard ceiling. Real agents have
phases (plan / implement / review / cleanup) that should each get a
share of the step budget, with a soft warning before the hard cut so
the agent has a chance to gracefully wrap up (commit work, write a
checkpoint, hand off).

This template provides:

- Per-phase budget allocation that sums to the total budget.
- Soft-warn threshold (default 80%) emitted exactly once per phase.
- A hard cut that raises ``BudgetExhausted`` so callers can convert it
  to a clean shutdown rather than an uncaught exception in the loop.
- A snapshot/report API for logging and post-mortem.

Contract
--------
- ``charge(phase, n=1)`` deducts ``n`` steps from ``phase``'s remaining
  budget. Returns a ``ChargeResult`` describing what happened and any
  warning that was crossed by this charge.
- ``charge`` raises ``BudgetExhausted`` if the charge would push the
  phase below zero remaining. The phase remaining is clamped to 0 in
  that case (no negative remaining stored).
- ``remaining(phase)`` and ``snapshot()`` are pure reads.

Edge cases
----------
- Phases not declared at construction time are rejected.
- Allocations must sum to ``total_budget`` exactly.
- ``warn_at`` of 1.0 effectively disables the soft warning.
- Calling ``charge(..., n=0)`` is a no-op (returns OK without warning).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional


class BudgetExhausted(RuntimeError):
    """Raised when a charge would exceed a phase's remaining budget."""

    def __init__(self, phase: str, requested: int, remaining: int) -> None:
        super().__init__(
            f"phase {phase!r} budget exhausted: requested {requested}, only {remaining} remaining"
        )
        self.phase = phase
        self.requested = requested
        self.remaining = remaining


@dataclass
class ChargeResult:
    phase: str
    charged: int
    remaining: int
    warned: bool  # True if THIS charge crossed the warn threshold


@dataclass
class StepBudgetMonitor:
    total_budget: int
    allocations: Mapping[str, int]
    warn_at: float = 0.80

    _spent: dict = field(default_factory=dict, init=False)
    _warned: dict = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.total_budget <= 0:
            raise ValueError("total_budget must be > 0")
        if not (0.0 < self.warn_at <= 1.0):
            raise ValueError("warn_at must be in (0.0, 1.0]")
        s = sum(self.allocations.values())
        if s != self.total_budget:
            raise ValueError(
                f"allocations sum to {s}, expected {self.total_budget}"
            )
        for phase, alloc in self.allocations.items():
            if alloc <= 0:
                raise ValueError(f"phase {phase!r} allocation must be > 0")
        self._spent = {p: 0 for p in self.allocations}
        self._warned = {p: False for p in self.allocations}

    def _check_phase(self, phase: str) -> None:
        if phase not in self.allocations:
            raise KeyError(f"unknown phase: {phase!r}")

    def remaining(self, phase: str) -> int:
        self._check_phase(phase)
        return self.allocations[phase] - self._spent[phase]

    def charge(self, phase: str, n: int = 1) -> ChargeResult:
        self._check_phase(phase)
        if n < 0:
            raise ValueError("n must be >= 0")
        if n == 0:
            return ChargeResult(phase=phase, charged=0, remaining=self.remaining(phase), warned=False)

        alloc = self.allocations[phase]
        before = self._spent[phase]
        after = before + n
        if after > alloc:
            # Don't store an over-spend; clamp to alloc so reporting is clean.
            self._spent[phase] = alloc
            raise BudgetExhausted(phase=phase, requested=n, remaining=alloc - before)

        self._spent[phase] = after
        remaining = alloc - after

        crossed_warn = False
        threshold = int(alloc * self.warn_at)
        if not self._warned[phase] and after >= threshold:
            self._warned[phase] = True
            crossed_warn = True

        return ChargeResult(phase=phase, charged=n, remaining=remaining, warned=crossed_warn)

    def snapshot(self) -> dict:
        rows = []
        for phase, alloc in self.allocations.items():
            spent = self._spent[phase]
            rows.append(
                {
                    "phase": phase,
                    "allocated": alloc,
                    "spent": spent,
                    "remaining": alloc - spent,
                    "pct_used": spent / alloc,
                    "warned": self._warned[phase],
                }
            )
        total_spent = sum(self._spent.values())
        return {
            "total_budget": self.total_budget,
            "total_spent": total_spent,
            "total_remaining": self.total_budget - total_spent,
            "phases": rows,
        }

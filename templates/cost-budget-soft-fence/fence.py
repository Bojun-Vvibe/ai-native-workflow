"""Soft-fence running token-cost ledger with warn rungs and refunds.

Hard cost caps (see ``agent-cost-budget-envelope``) tell the *next* call
"you can't spend"; this template tracks *already-spent* dollars against a
budget and emits structured warnings as you cross 60 / 85 / 95 % rungs
before the hard 100 % stop.

Every spend produces a structured ``Verdict``:

  - ``ok``           — under 60 %, no warning attached.
  - ``warn``         — crossed a warn rung; verdict carries ``rung`` and
                       ``next_rung`` so the caller can choose to back off
                       or stay the course. The same rung is never warned
                       on twice in one budget period (the ledger remembers
                       "already warned" rungs).
  - ``hard_stop``    — would exceed the 100 % budget; spend is REJECTED
                       and not appended to the ledger. The caller must
                       either (a) rollback or downsize the work, or
                       (b) raise the budget.

Refunds: a tool call that gets rolled back (transaction failed, agent loop
detected partial failure, idempotency dedup match) can issue a refund of a
previously committed spend by ``call_id``. Refunds:

  - Subtract the original committed amount from the running total.
  - Re-arm warn rungs that the running total has now dropped back below,
    so a recovered budget can warn again on the next genuine crossing
    (otherwise a refund-then-respend pattern silently masks the second
    crossing).
  - Are idempotent: refunding the same ``call_id`` twice returns
    ``status="already_refunded"`` and does not double-credit.
  - Cannot refund an unknown ``call_id`` (returns ``status="unknown"``).

Stdlib only; deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Warn rungs as fraction of budget. Order matters; must be sorted ascending
# strictly less than 1.0.
DEFAULT_WARN_RUNGS: tuple[float, ...] = (0.60, 0.85, 0.95)


class BudgetError(ValueError):
    pass


def _validate_rungs(rungs: tuple[float, ...]) -> None:
    if not rungs:
        raise BudgetError("warn_rungs must be non-empty")
    if list(rungs) != sorted(rungs):
        raise BudgetError(f"warn_rungs must be ascending, got {rungs}")
    if rungs[0] <= 0 or rungs[-1] >= 1.0:
        raise BudgetError(
            f"warn_rungs must be strictly between 0 and 1, got {rungs}"
        )


@dataclass
class Spend:
    call_id: str
    amount_usd: float
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id:
            raise BudgetError("call_id must be a non-empty string")
        if not isinstance(self.amount_usd, (int, float)):
            raise BudgetError("amount_usd must be numeric")
        if self.amount_usd < 0:
            raise BudgetError(
                f"amount_usd must be >= 0 for spend, got {self.amount_usd}"
            )


@dataclass
class Verdict:
    status: str  # ok | warn | hard_stop
    spent_after_usd: float
    fraction_after: float
    headroom_usd: float
    rung: float | None = None
    next_rung: float | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "spent_after_usd": round(self.spent_after_usd, 6),
            "fraction_after": round(self.fraction_after, 6),
            "headroom_usd": round(self.headroom_usd, 6),
            "rung": self.rung,
            "next_rung": self.next_rung,
            "reason": self.reason,
        }


@dataclass
class Ledger:
    """Running per-period spend ledger.

    The same instance handles multiple ``charge``/``refund`` calls and is
    the canonical state. Persist by serializing ``to_dict`` and
    re-hydrating with ``from_dict`` between processes.
    """

    budget_usd: float
    warn_rungs: tuple[float, ...] = DEFAULT_WARN_RUNGS
    spent_usd: float = 0.0
    warned_rungs: set[float] = field(default_factory=set)
    committed: dict[str, float] = field(default_factory=dict)  # call_id -> amount
    refunded: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.budget_usd <= 0:
            raise BudgetError(f"budget_usd must be > 0, got {self.budget_usd}")
        _validate_rungs(self.warn_rungs)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def charge(self, spend: Spend) -> Verdict:
        if spend.call_id in self.committed or spend.call_id in self.refunded:
            raise BudgetError(f"duplicate call_id: {spend.call_id!r}")
        projected = self.spent_usd + spend.amount_usd
        if projected > self.budget_usd + 1e-12:
            return Verdict(
                status="hard_stop",
                spent_after_usd=self.spent_usd,
                fraction_after=self.spent_usd / self.budget_usd,
                headroom_usd=max(0.0, self.budget_usd - self.spent_usd),
                reason=(
                    f"would exceed budget: spend {spend.amount_usd:.6f} + "
                    f"committed {self.spent_usd:.6f} > budget {self.budget_usd:.6f}"
                ),
            )

        self.spent_usd = projected
        self.committed[spend.call_id] = spend.amount_usd

        # Determine highest rung crossed by THIS spend that hasn't been warned.
        fraction = self.spent_usd / self.budget_usd
        crossed = [r for r in self.warn_rungs if fraction >= r and r not in self.warned_rungs]
        if crossed:
            rung = crossed[-1]
            # Mark every rung at or below this one as warned (single charge can
            # leap multiple rungs; we only emit one verdict but block re-warn
            # for the skipped rungs too).
            for r in self.warn_rungs:
                if r <= rung:
                    self.warned_rungs.add(r)
            higher = [r for r in self.warn_rungs if r > rung]
            return Verdict(
                status="warn",
                spent_after_usd=self.spent_usd,
                fraction_after=fraction,
                headroom_usd=self.budget_usd - self.spent_usd,
                rung=rung,
                next_rung=higher[0] if higher else None,
            )
        return Verdict(
            status="ok",
            spent_after_usd=self.spent_usd,
            fraction_after=fraction,
            headroom_usd=self.budget_usd - self.spent_usd,
        )

    def refund(self, call_id: str) -> dict[str, Any]:
        if call_id in self.refunded:
            return {
                "status": "already_refunded",
                "call_id": call_id,
                "spent_after_usd": round(self.spent_usd, 6),
            }
        if call_id not in self.committed:
            return {"status": "unknown", "call_id": call_id}
        amount = self.committed.pop(call_id)
        self.refunded.add(call_id)
        self.spent_usd = max(0.0, self.spent_usd - amount)
        # Re-arm warn rungs the running total has now dropped back below, so
        # a refund-then-respend can re-warn (otherwise the second crossing is
        # silent).
        fraction = self.spent_usd / self.budget_usd
        rearmed = sorted(r for r in list(self.warned_rungs) if fraction < r)
        for r in rearmed:
            self.warned_rungs.discard(r)
        return {
            "status": "refunded",
            "call_id": call_id,
            "amount_usd": round(amount, 6),
            "spent_after_usd": round(self.spent_usd, 6),
            "fraction_after": round(fraction, 6),
            "rearmed_rungs": rearmed,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_usd": self.budget_usd,
            "warn_rungs": list(self.warn_rungs),
            "spent_usd": round(self.spent_usd, 6),
            "warned_rungs": sorted(self.warned_rungs),
            "committed": dict(sorted(self.committed.items())),
            "refunded": sorted(self.refunded),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Ledger":
        return cls(
            budget_usd=float(d["budget_usd"]),
            warn_rungs=tuple(d.get("warn_rungs") or DEFAULT_WARN_RUNGS),
            spent_usd=float(d.get("spent_usd", 0.0)),
            warned_rungs=set(d.get("warned_rungs") or []),
            committed={k: float(v) for k, v in (d.get("committed") or {}).items()},
            refunded=set(d.get("refunded") or []),
        )


__all__ = [
    "Ledger",
    "Spend",
    "Verdict",
    "BudgetError",
    "DEFAULT_WARN_RUNGS",
]

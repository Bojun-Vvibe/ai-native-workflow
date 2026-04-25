#!/usr/bin/env python3
"""Project remaining tool-call budget runway from a recent spend window.

Given:
  - a hard budget for tool-call cost over the mission (e.g. $5.00, or
    50_000 tokens, or 200 calls — units are caller-owned),
  - a chronological list of (timestamp_seconds, cost) spend events,
  - a "now" timestamp,

compute:
  - spent_total: sum of all spend up to now
  - remaining: budget - spent_total
  - window_spend: spend strictly inside (now - window_seconds, now]
  - burn_rate_per_sec: window_spend / window_seconds   (0 if window empty)
  - eta_seconds: remaining / burn_rate_per_sec         (None if burn=0)
  - verdict: one of
      "ok"        — under soft fence, projected runway >= remaining mission time
      "warn"      — over soft fence (default 0.6 of budget) but under hard fence
      "throttle"  — over hard fence (default 0.85 of budget) — caller should
                    refuse new non-critical tool calls
      "exhausted" — spent_total >= budget; no more spend allowed
      "no_signal" — empty spend list (cannot project anything yet)

This is the *projector* that fires *before* `agent-step-budget-monitor`'s
hard wall — the goal is to surface "you will run out in 90 seconds" while
the agent still has time to gracefully degrade (drop optional sub-agents,
switch to cheaper model, hand off with `partial`), instead of hitting a
mid-tool-call exception.

Pure stdlib. Pure function over an in-memory list — no I/O, no clocks.
The `now` value is injected for deterministic testing.

Why a windowed burn rate (not all-time average)?
  - Missions have phases. A scout phase might burn 10% of budget in 5s
    of parallel reads, then sit idle for 60s while the actor thinks.
    All-time average says "you have 4 hours left"; windowed says "at
    your current rate you have 12s left." The latter is the actionable
    signal.
  - `window_seconds` should match the dispatcher's check cadence — if
    the host re-checks every 30s, a 60s window gives 2 ticks of
    smoothing without lagging behind a real spike.

Edge cases handled:
  - Spend events at exactly `now - window_seconds` are *excluded* (open
    lower bound) so a one-shot 30s window does not double-count an
    event sitting on the boundary across two consecutive ticks.
  - `eta_seconds` is `None`, not infinity, when burn rate is zero —
    JSON-serializable and unambiguous.
  - Negative `remaining` clamps eta to `0.0` (you are already over).
  - Out-of-order timestamps raise `BudgetInputError` — silently
    re-sorting would mask an upstream instrumentation bug.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from typing import Any


class BudgetInputError(ValueError):
    pass


@dataclass
class Projection:
    spent_total: float
    remaining: float
    window_seconds: float
    window_spend: float
    burn_rate_per_sec: float
    eta_seconds: float | None
    fraction_spent: float
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def project(
    *,
    budget: float,
    spend: list[tuple[float, float]],
    now: float,
    window_seconds: float = 60.0,
    soft_fence: float = 0.6,
    hard_fence: float = 0.85,
) -> Projection:
    if budget <= 0:
        raise BudgetInputError(f"budget must be > 0, got {budget!r}")
    if window_seconds <= 0:
        raise BudgetInputError(f"window_seconds must be > 0, got {window_seconds!r}")
    if not (0.0 < soft_fence < hard_fence < 1.0):
        raise BudgetInputError(
            f"require 0 < soft_fence < hard_fence < 1; got soft={soft_fence}, hard={hard_fence}"
        )

    last_ts: float | None = None
    spent_total = 0.0
    window_spend = 0.0
    window_lo = now - window_seconds

    for i, ev in enumerate(spend):
        if not (isinstance(ev, (list, tuple)) and len(ev) == 2):
            raise BudgetInputError(f"spend[{i}] must be (timestamp, cost) pair, got {ev!r}")
        ts, cost = ev
        if not isinstance(ts, (int, float)) or not isinstance(cost, (int, float)):
            raise BudgetInputError(f"spend[{i}] must be numeric, got ({ts!r}, {cost!r})")
        if cost < 0:
            raise BudgetInputError(f"spend[{i}] cost must be >= 0, got {cost!r}")
        if last_ts is not None and ts < last_ts:
            raise BudgetInputError(
                f"spend timestamps must be non-decreasing; spend[{i}].ts={ts} < previous {last_ts}"
            )
        last_ts = ts
        if ts > now:
            # Future events are not part of "spent" — caller bug or clock skew.
            # Silent drop is wrong; fail loud.
            raise BudgetInputError(
                f"spend[{i}].ts={ts} is in the future relative to now={now}"
            )
        spent_total += float(cost)
        if ts > window_lo:  # strict: events at exactly window_lo are excluded
            window_spend += float(cost)

    remaining = budget - spent_total
    fraction_spent = spent_total / budget

    burn_rate = window_spend / window_seconds
    if burn_rate <= 0:
        eta: float | None = None
    elif remaining <= 0:
        eta = 0.0
    else:
        eta = remaining / burn_rate

    if not spend:
        verdict = "no_signal"
    elif spent_total >= budget:
        verdict = "exhausted"
    elif fraction_spent >= hard_fence:
        verdict = "throttle"
    elif fraction_spent >= soft_fence:
        verdict = "warn"
    else:
        verdict = "ok"

    return Projection(
        spent_total=round(spent_total, 6),
        remaining=round(remaining, 6),
        window_seconds=window_seconds,
        window_spend=round(window_spend, 6),
        burn_rate_per_sec=round(burn_rate, 6),
        eta_seconds=(round(eta, 3) if eta is not None else None),
        fraction_spent=round(fraction_spent, 6),
        verdict=verdict,
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: project.py <input.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    cases = doc.get("cases")
    if not isinstance(cases, list):
        raise BudgetInputError("input.cases must be a list")

    out: list[dict[str, Any]] = []
    for case in cases:
        spend_pairs = [tuple(ev) for ev in case.get("spend", [])]
        try:
            proj = project(
                budget=case["budget"],
                spend=spend_pairs,
                now=case["now"],
                window_seconds=case.get("window_seconds", 60.0),
                soft_fence=case.get("soft_fence", 0.6),
                hard_fence=case.get("hard_fence", 0.85),
            )
            out.append({"name": case.get("name", "?"), "result": proj.to_dict()})
        except BudgetInputError as e:
            out.append({"name": case.get("name", "?"), "error": str(e)})

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

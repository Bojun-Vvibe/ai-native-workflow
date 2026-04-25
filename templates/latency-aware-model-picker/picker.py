"""Latency-aware model picker.

The problem: an orchestrator has N model rungs that can plausibly serve
the same request (e.g. fast-cheap, mid-balanced, big-smart). Picking
purely on cost is wrong when one rung's tail latency has just blown up;
picking purely on observed latency is wrong when a rung is fast because
nobody's been able to use it (selection bias). This module is a pure
*picker*: it consumes a small rolling stats window per rung and a
declarative `LatencyPolicy`, and returns one of:

  - `Pick(rung_id=..., reason=...)`         — go ahead, use this rung
  - `Defer(reason=..., suggested_wait_s=...)`  — every rung is unhealthy
                                                 right now; back off

It does NOT call any model. It does NOT update the stats; the caller
records each call's outcome via `Stats.observe(latency_s, ok)` and
passes the resulting Stats object back in next time.

Design choices:

- The latency signal is the rolling **p95**, not the mean. p95 is what
  agent users actually feel; means hide tail blowups under steady-state
  traffic.
- A rung needs `min_observations` data points before its p95 is
  trusted. Below that floor it's treated as `unknown_latency` and only
  picked if every other rung is exhausted (a cold rung is better than
  no rung).
- Failure-rate is a hard gate (rung is unhealthy if `failure_rate >
  max_failure_rate`), evaluated BEFORE p95. A 100ms rung that fails
  60% of calls is worse than a 2s rung that succeeds.
- Tie-break order on the eligible set is: lower p95 wins, then lower
  cost, then declared rung order. This is deliberate — once a rung is
  inside the latency budget, cost is the next most important lever.
- `Defer` is returned with `suggested_wait_s` set to the shortest known
  p95 of any unhealthy-by-failure rung, so the caller can sleep ~one
  request worth of time before re-checking. If no rung has any data,
  we suggest `policy.cold_defer_s`.

Stdlib-only. No I/O, no clocks (caller passes timestamps if it wants).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


class PickerConfigError(ValueError):
    pass


@dataclass
class Stats:
    """Rolling per-rung stats. Pure data; the caller mutates via observe()."""

    window: int = 50
    latencies_s: deque = field(default_factory=lambda: deque(maxlen=50))
    successes: deque = field(default_factory=lambda: deque(maxlen=50))

    def __post_init__(self) -> None:
        if self.window < 5:
            raise PickerConfigError("window must be >= 5")
        # rebuild deques with the configured maxlen if caller passed window
        self.latencies_s = deque(self.latencies_s, maxlen=self.window)
        self.successes = deque(self.successes, maxlen=self.window)

    def observe(self, latency_s: float, ok: bool) -> None:
        if latency_s < 0 or not math.isfinite(latency_s):
            raise PickerConfigError(f"latency_s must be finite and >= 0, got {latency_s!r}")
        self.latencies_s.append(latency_s)
        self.successes.append(1 if ok else 0)

    @property
    def n(self) -> int:
        return len(self.latencies_s)

    @property
    def failure_rate(self) -> float:
        if not self.successes:
            return 0.0
        return 1.0 - (sum(self.successes) / len(self.successes))

    @property
    def p95(self) -> float | None:
        if not self.latencies_s:
            return None
        s = sorted(self.latencies_s)
        # nearest-rank: ceil(0.95 * N) - 1 (clamped)
        idx = max(0, min(len(s) - 1, math.ceil(0.95 * len(s)) - 1))
        return s[idx]


@dataclass(frozen=True)
class Rung:
    rung_id: str
    cost_per_call_usd: float

    def __post_init__(self) -> None:
        if self.cost_per_call_usd < 0 or not math.isfinite(self.cost_per_call_usd):
            raise PickerConfigError(f"cost_per_call_usd must be finite and >= 0 for {self.rung_id!r}")


@dataclass(frozen=True)
class LatencyPolicy:
    p95_budget_s: float
    max_failure_rate: float = 0.20
    min_observations: int = 5
    cold_defer_s: float = 1.0

    def __post_init__(self) -> None:
        if self.p95_budget_s <= 0:
            raise PickerConfigError("p95_budget_s must be > 0")
        if not 0.0 <= self.max_failure_rate < 1.0:
            raise PickerConfigError("max_failure_rate must be in [0, 1)")
        if self.min_observations < 1:
            raise PickerConfigError("min_observations must be >= 1")


@dataclass(frozen=True)
class Pick:
    verdict: str  # "pick"
    rung_id: str
    reason: str
    p95_s: float | None
    failure_rate: float
    n: int


@dataclass(frozen=True)
class Defer:
    verdict: str  # "defer"
    reason: str
    suggested_wait_s: float


def pick(
    rungs: Iterable[Rung],
    stats_by_rung: dict,
    policy: LatencyPolicy,
) -> Pick | Defer:
    """Pure picker.

    `rungs`: declared in caller-preferred order (used as final tiebreak).
    `stats_by_rung`: dict[rung_id -> Stats]. Missing rungs are treated as
        cold (no observations).
    `policy`: latency budget + failure tolerance.

    Returns Pick(...) or Defer(...).
    """
    rungs = list(rungs)
    if not rungs:
        raise PickerConfigError("at least one rung is required")

    eligible: list[tuple[Rung, Stats, float]] = []  # (rung, stats, p95)
    cold: list[Rung] = []
    unhealthy_p95s: list[float] = []

    for rung in rungs:
        st = stats_by_rung.get(rung.rung_id) or Stats()
        if st.n < policy.min_observations:
            cold.append(rung)
            continue
        # Check failure rate first — a fast-but-broken rung is not eligible.
        if st.failure_rate > policy.max_failure_rate:
            p95 = st.p95
            if p95 is not None:
                unhealthy_p95s.append(p95)
            continue
        # Then check p95 budget.
        p95 = st.p95
        assert p95 is not None  # n >= min_observations guarantees data
        if p95 > policy.p95_budget_s:
            unhealthy_p95s.append(p95)
            continue
        eligible.append((rung, st, p95))

    if eligible:
        # Tiebreak: lower p95, then lower cost, then declared order.
        order_index = {r.rung_id: i for i, r in enumerate(rungs)}
        eligible.sort(key=lambda t: (t[2], t[0].cost_per_call_usd, order_index[t[0].rung_id]))
        winner_rung, winner_stats, winner_p95 = eligible[0]
        return Pick(
            verdict="pick",
            rung_id=winner_rung.rung_id,
            reason="within_budget",
            p95_s=winner_p95,
            failure_rate=winner_stats.failure_rate,
            n=winner_stats.n,
        )

    # No rung has both enough observations AND a healthy p95+failure_rate.
    # Fall back to a cold rung if any — better to sample a cold rung than
    # to defer indefinitely.
    if cold:
        chosen = cold[0]  # declared order — caller's preference wins
        st = stats_by_rung.get(chosen.rung_id) or Stats()
        return Pick(
            verdict="pick",
            rung_id=chosen.rung_id,
            reason="cold_rung_sampled",
            p95_s=st.p95,
            failure_rate=st.failure_rate,
            n=st.n,
        )

    # Every rung has data and every rung is unhealthy. Defer.
    if unhealthy_p95s:
        wait = min(unhealthy_p95s)
    else:
        wait = policy.cold_defer_s
    return Defer(
        verdict="defer",
        reason="all_rungs_unhealthy",
        suggested_wait_s=wait,
    )

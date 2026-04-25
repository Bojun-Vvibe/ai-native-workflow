"""End-to-end worked example for the latency-aware model picker.

Three rungs, three scenarios:

  1. Steady-state. All rungs healthy. Picker picks the lowest-p95 one
     (which is also the cheapest in this setup) — verdict=pick,
     reason=within_budget.

  2. Mid-rung tail blowup. The mid rung's p95 jumps over the budget.
     Picker switches to the next-best rung within budget rather than
     stubbornly picking by cost.

  3. All rungs degraded. Every rung is either over the latency budget
     OR over the failure-rate ceiling. Picker returns Defer with a
     sensible suggested_wait_s drawn from the fastest unhealthy rung.

  4. Cold rung. The big rung has zero observations; the others are
     unhealthy. Picker samples the cold rung instead of deferring —
     proves the cold-rung-sampling fallback works.

  5. Fast-but-broken. The fast rung has p95=0.05s but a 60% failure
     rate; the mid rung has p95=0.40s and 0% failure rate. Picker
     correctly rejects the fast-broken rung on failure-rate grounds.
"""

from __future__ import annotations

from dataclasses import asdict

from picker import LatencyPolicy, Rung, Stats, pick


def populate(stats: Stats, latencies: list[float], successes: list[bool]) -> Stats:
    assert len(latencies) == len(successes)
    for lat, ok in zip(latencies, successes):
        stats.observe(lat, ok)
    return stats


def render(verdict) -> None:
    d = asdict(verdict)
    for k, v in d.items():
        print(f"    {k} = {v!r}")


def header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# Three declared rungs in caller-preferred (= cheap-to-expensive) order.
rungs = [
    Rung(rung_id="fast-cheap", cost_per_call_usd=0.0005),
    Rung(rung_id="mid-balanced", cost_per_call_usd=0.0040),
    Rung(rung_id="big-smart", cost_per_call_usd=0.0250),
]

policy = LatencyPolicy(
    p95_budget_s=2.0,
    max_failure_rate=0.20,
    min_observations=10,
    cold_defer_s=1.0,
)


# ----- Case 1: steady-state, everyone healthy -----
header("Case 1: steady-state — all rungs healthy")
case1 = {
    "fast-cheap":   populate(Stats(window=50), [0.30, 0.32, 0.28, 0.31, 0.29, 0.33, 0.30, 0.31, 0.30, 0.34, 0.30, 0.30], [True] * 12),
    "mid-balanced": populate(Stats(window=50), [0.50, 0.55, 0.48, 0.52, 0.51, 0.49, 0.53, 0.50, 0.52, 0.55, 0.51, 0.50], [True] * 12),
    "big-smart":    populate(Stats(window=50), [1.20, 1.30, 1.25, 1.28, 1.22, 1.31, 1.27, 1.24, 1.26, 1.29, 1.25, 1.25], [True] * 12),
}
print("p95s:", {k: round(v.p95, 3) for k, v in case1.items()})
print("verdict:")
render(pick(rungs, case1, policy))

# ----- Case 2: mid-rung tail blowup -----
header("Case 2: mid-rung tail blowup — picker should skip mid")
case2 = {
    "fast-cheap":   populate(Stats(window=50), [0.30] * 10 + [3.5, 4.0], [True] * 12),  # rare slow tail BUT p95 still high
    "mid-balanced": populate(Stats(window=50), [0.50] * 8 + [12.0, 11.0, 13.0, 12.5], [True] * 12),  # p95 blew up to ~13s
    "big-smart":    populate(Stats(window=50), [1.20, 1.30, 1.25, 1.28, 1.22, 1.31, 1.27, 1.24, 1.26, 1.29, 1.25, 1.25], [True] * 12),
}
print("p95s:", {k: round(v.p95, 3) for k, v in case2.items()})
print("verdict:")
render(pick(rungs, case2, policy))

# ----- Case 3: all rungs degraded -----
header("Case 3: all rungs degraded — should defer")
case3 = {
    "fast-cheap":   populate(Stats(window=50), [5.0] * 12, [True] * 12),                # p95=5s > 2s budget
    "mid-balanced": populate(Stats(window=50), [4.0] * 12, [True] * 12),                # p95=4s > 2s budget
    "big-smart":    populate(Stats(window=50), [0.5] * 12, [False, False, False, False, False, False, False, True, True, True, True, True]),  # 7/12 fail = 58%
}
print("p95s:", {k: round(v.p95, 3) for k, v in case3.items()})
print("failure_rates:", {k: round(v.failure_rate, 3) for k, v in case3.items()})
print("verdict:")
render(pick(rungs, case3, policy))

# ----- Case 4: cold rung available -----
header("Case 4: cold rung available — sample it instead of deferring")
case4 = {
    "fast-cheap":   populate(Stats(window=50), [5.0] * 12, [True] * 12),  # over budget
    "mid-balanced": populate(Stats(window=50), [4.0] * 12, [True] * 12),  # over budget
    # big-smart: no observations at all -> cold
}
print("p95s:", {k: round(v.p95, 3) for k, v in case4.items()}, "(big-smart=COLD)")
print("verdict:")
render(pick(rungs, case4, policy))

# ----- Case 5: fast-but-broken vs slow-but-reliable -----
header("Case 5: fast-but-broken — failure rate beats raw latency")
case5 = {
    "fast-cheap":   populate(Stats(window=50), [0.05] * 12, [False, False, False, False, False, False, False, True, True, True, True, True]),  # 7/12 fail
    "mid-balanced": populate(Stats(window=50), [0.40] * 12, [True] * 12),  # healthy
    "big-smart":    populate(Stats(window=50), [1.20] * 12, [True] * 12),  # healthy
}
print("p95s:", {k: round(v.p95, 3) for k, v in case5.items()})
print("failure_rates:", {k: round(v.failure_rate, 3) for k, v in case5.items()})
print("verdict:")
render(pick(rungs, case5, policy))

print()
print("=" * 70)
print("ALL CASES EVALUATED.")
print("=" * 70)

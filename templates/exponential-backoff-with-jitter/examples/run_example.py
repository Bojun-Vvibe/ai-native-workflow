"""Worked example: four jitter strategies under the same policy + budget truncation.

Deterministic RNG (seed=7) so output is byte-stable across runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).parent.parent))
from backoff import BackoffPolicy, plan, truncate_to_budget


def fmt(schedule):
    return [(i, round(d, 4)) for i, d in schedule]


def main() -> None:
    policy = BackoffPolicy(base_s=0.5, cap_s=8.0, jitter="none")
    print("Scenario A: same (base=0.5, cap=8.0), 6 attempts, four jitter kinds")
    print("-" * 70)
    for kind in ("none", "full", "equal", "decorrelated"):
        rng = Random(7)
        p = BackoffPolicy(base_s=0.5, cap_s=8.0, jitter=kind)
        sched = plan(p, attempts_total=6, rng=rng)
        cum = round(sum(d for _, d in sched), 4)
        print(f"  jitter={kind:13s} schedule={fmt(sched)}  cumulative={cum}s")

    print()
    print("Scenario B: truncate a 6-attempt 'none' plan to a 5.0s wall-clock budget")
    print("-" * 70)
    rng = Random(7)
    p = BackoffPolicy(base_s=0.5, cap_s=8.0, jitter="none")
    full = plan(p, attempts_total=6, rng=rng)
    print(f"  full plan       = {fmt(full)}")
    fits = truncate_to_budget(full, budget_s=5.0)
    print(f"  fits in 5.0s    = {fmt(fits)}")
    print(f"  retries kept    = {len(fits)} of {len(full)}")
    print(f"  cumulative_kept = {round(sum(d for _, d in fits), 4)}s")

    print()
    print("Scenario C: attempts_total=1 → no retries, empty plan")
    print("-" * 70)
    rng = Random(7)
    empty = plan(policy, attempts_total=1, rng=rng)
    print(f"  plan(attempts_total=1) = {empty}")


if __name__ == "__main__":
    main()

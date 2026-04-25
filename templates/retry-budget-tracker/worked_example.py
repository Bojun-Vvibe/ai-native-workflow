"""Worked example for retry-budget-tracker.

Simulates 8 concurrent logical calls hitting a flaky endpoint with a
60% transient failure rate. A SHARED retry budget of 5 tokens, refilling
at 1 token/sec, prevents the 8 callers from collectively burning through
unbounded retries during a brownout.

Run:  python3 worked_example.py
"""

from __future__ import annotations

import random
import threading

from retry_budget import (
    BudgetExhausted,
    RetryBudget,
    RetryStats,
    call_with_budget,
)


def make_flaky(name: str, seed: int, fail_rate: float = 0.6):
    rng = random.Random(seed)
    counter = {"n": 0}

    def fn():
        counter["n"] += 1
        if rng.random() < fail_rate:
            raise ConnectionError(f"{name}: transient blip #{counter['n']}")
        return f"{name}:ok-on-attempt-{counter['n']}"

    return fn


def worker(name: str, seed: int, budget: RetryBudget, stats: RetryStats, results: list[str]) -> None:
    fn = make_flaky(name, seed)
    try:
        out = call_with_budget(
            fn,
            budget=budget,
            per_call_max=4,
            stats=stats,
            backoff_base=0.0,  # no real sleep in the example
        )
        results.append(f"OK   {name} -> {out}")
    except BudgetExhausted as e:
        results.append(f"DENY {name} -> {e}")
    except Exception as e:
        results.append(f"FAIL {name} -> {e!r}")


def main() -> None:
    # Shared budget across all 8 workers. Capacity 5, slow refill.
    budget = RetryBudget(capacity=5, refill_per_sec=1.0)
    stats = RetryStats()
    results: list[str] = []

    threads: list[threading.Thread] = []
    for i in range(8):
        t = threading.Thread(
            target=worker,
            args=(f"call-{i}", 1000 + i, budget, stats, results),
        )
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    print("=== per-call outcomes ===")
    for line in results:
        print(line)

    print()
    print("=== aggregate stats ===")
    print(f"attempts        : {stats.attempts}")
    print(f"successes       : {stats.successes}")
    print(f"failures        : {stats.failures}")
    print(f"retries_used    : {stats.retries_used}")
    print(f"retries_denied  : {stats.retries_denied}")
    print(f"tokens_remaining: {budget.tokens():.2f}")

    # Sanity: retries_used must never exceed initial capacity (no refill in this fast run).
    assert stats.retries_used <= 5, "shared budget cap was breached!"
    print()
    print("invariant OK: retries_used <= capacity (5)")


if __name__ == "__main__":
    main()

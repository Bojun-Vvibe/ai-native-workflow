"""End-to-end demo of StepBudgetMonitor.

Simulates a 4-phase agent (plan, implement, review, cleanup) with a
total budget of 20 steps. Implementation phase is intentionally
overworked to trigger the soft warn AND the hard cut, and the cleanup
phase still gets to run because it has its own allocation.
"""

from __future__ import annotations

from monitor import StepBudgetMonitor, BudgetExhausted


def run_phase(monitor: StepBudgetMonitor, phase: str, want: int) -> int:
    """Try to do `want` steps in `phase`. Returns how many actually ran."""
    done = 0
    for _ in range(want):
        try:
            r = monitor.charge(phase, 1)
        except BudgetExhausted as e:
            print(f"  [HARD] {phase}: exhausted after {done} steps ({e})")
            break
        done += 1
        if r.warned:
            print(f"  [WARN] {phase}: crossed {int(monitor.warn_at * 100)}% soft threshold (remaining={r.remaining}); should wrap up")
    print(f"  {phase}: {done}/{want} steps completed (remaining={monitor.remaining(phase)})")
    return done


def main() -> None:
    monitor = StepBudgetMonitor(
        total_budget=20,
        allocations={
            "plan": 4,
            "implement": 10,
            "review": 4,
            "cleanup": 2,
        },
        warn_at=0.80,
    )

    print("=== plan ===")
    run_phase(monitor, "plan", want=3)

    print("=== implement (will overshoot) ===")
    run_phase(monitor, "implement", want=14)

    print("=== review ===")
    run_phase(monitor, "review", want=4)

    print("=== cleanup (still has its own budget) ===")
    run_phase(monitor, "cleanup", want=2)

    print()
    print("=== final snapshot ===")
    snap = monitor.snapshot()
    print(f"total: spent={snap['total_spent']}/{snap['total_budget']} remaining={snap['total_remaining']}")
    print(f"{'phase':<11} {'alloc':>5} {'spent':>5} {'rem':>4} {'pct':>6} warned")
    print("-" * 44)
    for row in snap["phases"]:
        print(
            f"{row['phase']:<11} {row['allocated']:>5} {row['spent']:>5} "
            f"{row['remaining']:>4} {row['pct_used']*100:>5.0f}% {row['warned']}"
        )


if __name__ == "__main__":
    main()

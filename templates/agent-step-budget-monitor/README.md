# agent-step-budget-monitor

A per-phase step budget for agent loops, with **soft warnings** before
the **hard cut**, so the agent gets a chance to wrap up cleanly instead
of crashing mid-thought.

## What

`StepBudgetMonitor(total_budget, allocations, warn_at=0.80)`:

- **Phase allocations** must sum exactly to `total_budget`. Each phase
  gets its own bucket — running `implement` dry doesn't starve
  `cleanup`.
- `charge(phase, n=1)` deducts `n` steps. Returns a `ChargeResult` with
  a `warned` flag that fires **once** per phase the moment cumulative
  spend crosses `warn_at` (default 80%).
- A charge that would overspend raises `BudgetExhausted` — the loop
  catches it, commits whatever partial work it has, and moves on.
- `snapshot()` gives a per-phase report for logs and post-mortems.

## Why (vs. the simpler templates)

- `agent-loop-iteration-cap` is a single hard ceiling. No phases, no
  warnings, no clean shutdown signal.
- `cost-budget-soft-fence` and `agent-cost-budget-envelope` track
  **dollars/tokens**, not **steps**. Step count is what actually
  governs agent latency and tool-call sprawl.
- `token-budget-tracker` is also dollar/token-focused.

This template fills the gap: "how many *iterations* can each phase of
my agent take, and how do I notice I'm about to run out *before* I do?"

## When to use it

- Multi-phase agents: plan → implement → review → cleanup, or
  research → synthesize → write.
- Loops where you want the agent to checkpoint/handoff before being
  killed mid-step.
- Anywhere you want per-phase observability ("review keeps blowing its
  budget; reallocate").

## When NOT to use it

- Single-phase loops with a flat ceiling — use
  `agent-loop-iteration-cap`.
- Cost/token control — use `cost-budget-soft-fence`.
- Distributed multi-worker budgets — this is in-process only.

## Contract & edge cases

- Allocations must sum to `total_budget` exactly; off-by-one is a
  config bug, not a runtime guess.
- Each phase allocation must be `> 0`. If you really want a phase to
  be no-op, omit it.
- `warn_at` in `(0.0, 1.0]`. `1.0` effectively disables the soft warn.
- `charge(phase, 0)` is a no-op. `charge(phase, n)` with `n < 0`
  raises.
- On `BudgetExhausted` the phase's spend is clamped to its allocation
  (no negative remaining stored), so `snapshot()` stays honest.

## Worked example output

```
=== plan ===
  [WARN] plan: crossed 80% soft threshold (remaining=1); should wrap up
  plan: 3/3 steps completed (remaining=1)
=== implement (will overshoot) ===
  [WARN] implement: crossed 80% soft threshold (remaining=2); should wrap up
  [HARD] implement: exhausted after 10 steps (phase 'implement' budget exhausted: requested 1, only 0 remaining)
  implement: 10/14 steps completed (remaining=0)
=== review ===
  [WARN] review: crossed 80% soft threshold (remaining=1); should wrap up
  review: 4/4 steps completed (remaining=0)
=== cleanup (still has its own budget) ===
  [WARN] cleanup: crossed 80% soft threshold (remaining=1); should wrap up
  cleanup: 2/2 steps completed (remaining=0)

=== final snapshot ===
total: spent=19/20 remaining=1
phase       alloc spent  rem    pct warned
--------------------------------------------
plan            4     3    1    75% True
implement      10    10    0   100% True
review          4     4    0   100% True
cleanup         2     2    0   100% True
```

Note `implement` blew its budget, but `review` and `cleanup` still ran
to completion because their allocations are isolated.

## Running

```bash
python3 worked_example.py
```

Stdlib only. No dependencies.

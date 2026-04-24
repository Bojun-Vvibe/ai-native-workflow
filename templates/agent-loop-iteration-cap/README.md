# agent-loop-iteration-cap

Defensive iteration cap for any agent control loop, with **stuck detection** (same observable state twice in a row), **exponential cooldown** between iterations once the agent starts spinning, a hard ceiling that always trips, and a structured `LoopOutcome` so the caller can route `done` / `stuck` / `exhausted` / `expired` to different recovery paths instead of treating "the loop returned" as a single uniform success signal.

## The pattern

Every agent that runs `while not done: pick_action(); apply()` is one prompt-engineering accident away from looping forever — a missing tool, a flapping return value, an LLM that cannot stop "checking one more thing." A wall-clock deadline alone does not save you: a 30-minute deadline against an agent that costs `$0.40` per iteration is `$720` per stuck session. An iteration count alone does not save you either: 50 iterations of the agent making real progress is fine, 50 iterations of the agent re-asking the same tool is a fire.

The cap composes four orthogonal stop conditions:

1. **`max_iterations`** — hard ceiling, always trips, regardless of progress. The "blow the breaker" of last resort.
2. **`deadline_at`** — wall-clock cap. Caller passes a monotonic clock function; the loop checks before each step.
3. **stuck-fingerprint** — caller passes a `fingerprint(state) -> str` callable. If the same fingerprint appears `stuck_threshold` (default 2) consecutive iterations, the loop bails with `outcome="stuck"`. This catches the common case of "tool returned the same thing, agent had no new info, agent will ask again."
4. **exponential cooldown** — once `consecutive_no_progress >= cooldown_after` (default 1), sleep `min(base_cooldown_s * 2**(n - cooldown_after), max_cooldown_s)` before the next iteration. Burns wall clock cheaply instead of burning model tokens, while leaving room for an observably-progressing agent to recover. Set `base_cooldown_s=0.0` to disable.

The loop function itself does **not** call the model — it accepts a `step(state) -> StepResult(state, done, observable)` callable so the agent surface stays composable with `tool-call-retry-envelope`, `agent-cost-budget-envelope`, and friends. The cap is policy; `step` is mechanism.

## When to use it

- **Wrapping any iterative agent loop in production.** The default config (`max_iterations=20`, `stuck_threshold=2`, `base_cooldown_s=1.0`, `max_cooldown_s=30.0`) is a sane starting point for tool-augmented chat agents.
- **Background/cron agents.** A scheduled "investigate today's CI failures" agent that runs unattended must have a hard ceiling — pager noise from a stuck agent is much worse than a missed investigation.
- **Multi-agent orchestrators.** Each child gets its own cap; the orchestrator routes `outcome="stuck"` to a different child rather than asking the same child harder.
- **Repair loops.** `structured-output-repair-loop` is a special case of this pattern with a fingerprint that hashes the validator error class.

## When NOT to use it

- **For one-shot agents.** A single LLM call with a single tool call does not need a loop cap — it is not a loop.
- **As a substitute for cost budgets.** A `max_iterations=20` cap with a $5/call agent is still a $100 disaster. Stack `agent-cost-budget-envelope` *underneath* this for the money side. The iteration cap controls *spinning*; the cost envelope controls *spending*.
- **For long-running deterministic search algorithms.** A graph search with 10,000 deterministic-progress steps and no model calls does not benefit. Use a dedicated profiler.
- **When you need exact convergence semantics.** This is a defensive backstop, not a fixpoint detector. If your loop genuinely converges, write a real `is_fixpoint()` check; the iteration cap should never fire on a healthy run.

## Alternatives and how they differ

- **Bare `for _ in range(N):`** — a hard ceiling, nothing else. Misses the "agent is spinning *under* the ceiling" case which is the more common failure mode.
- **`structured-output-repair-loop`** — domain-specific (output validation), uses an error-fingerprint and a stuck check. This template is the generalisation: any state, any fingerprint.
- **`tool-call-circuit-breaker`** — trips on *failure rate* of a specific dependency. Iteration cap trips on *agent-loop pathology* regardless of whether the underlying tools are healthy. They compose: a healthy tool with an unhealthy agent still trips this cap.
- **Wall-clock `signal.alarm`** — interrupts mid-call. Iteration cap waits for a clean step boundary, so the next observable state is consistent. Use both if you also need to defend against a single step that hangs forever.

## Composition

```
caller --(state)--> [iteration_cap] --(state)--> step()
                       |                         /|\
                       |                          |
                       +-- fingerprint(state) ----+
                       +-- now() ------------------ wall clock
                       +-- sleep() ---------------- cooldown
```

`step()` is yours. Pass `now`, `sleep`, and `fingerprint` as injected callables so the loop is fully deterministic in tests (the worked example uses a fake clock and a list-backed sleep recorder — no real wall-clock waits during the test, but the cooldown math is exercised end-to-end).

`LoopOutcome` is `done | stuck | exhausted | expired`, plus `iterations`, `final_state`, `cooldowns_applied`, `total_cooldown_s`, and `stuck_fingerprint` (when applicable). Caller pattern-matches and routes:

- `done` → continue.
- `stuck` → escalate to a different agent / human / fallback (the agent saw the same world twice; running it again will produce the same answer).
- `exhausted` → likely a hard problem; consider a richer model or a smaller subproblem.
- `expired` → wall-clock budget too tight; either widen the deadline or break the work into chunks.

## Failure modes the implementation defends against

1. **Cap of 0.** Treated as "do not run" — returns `exhausted` with `iterations=0` instead of crashing.
2. **Fingerprint that throws.** Wrapped; the loop bails with a `LoopError` so a buggy fingerprint cannot mask a real loop.
3. **`step` that mutates state in place but also returns a new object.** The loop uses the *returned* state, never the input — so an aliasing mistake does not silently use stale state.
4. **Negative cooldowns / huge max_cooldown.** Clamped at construction.

## Files in this template

- `iteration_cap.py` — stdlib-only reference (≈140 lines).
- `example.py` — four-part worked example: a healthy converging loop (`done`), a spinning loop caught by the stuck detector with two cooldowns applied (`stuck`), a slow-but-progressing loop that hits `max_iterations` (`exhausted`), and a long loop that trips the deadline (`expired`).

"""Defensive iteration cap for agent control loops.

Stdlib-only. now/sleep/fingerprint are injected callables so the loop is
deterministic in tests and composable in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class LoopError(Exception):
    """Internal error inside the cap (buggy fingerprint, bad config, etc.)."""


@dataclass
class StepResult:
    state: Any
    done: bool
    observable: Any = None  # optional human-readable progress marker


@dataclass
class LoopOutcome:
    outcome: str  # 'done' | 'stuck' | 'exhausted' | 'expired'
    iterations: int
    final_state: Any
    cooldowns_applied: int = 0
    total_cooldown_s: float = 0.0
    stuck_fingerprint: str | None = None
    fingerprints: list[str] = field(default_factory=list)


def run_with_cap(
    initial_state: Any,
    step: Callable[[Any], StepResult],
    *,
    fingerprint: Callable[[Any], str],
    max_iterations: int = 20,
    deadline_at: float | None = None,
    stuck_threshold: int = 2,
    cooldown_after: int = 1,
    base_cooldown_s: float = 1.0,
    max_cooldown_s: float = 30.0,
    now: Callable[[], float] = None,  # type: ignore[assignment]
    sleep: Callable[[float], None] = None,  # type: ignore[assignment]
) -> LoopOutcome:
    """Run `step` repeatedly until one of the four stop conditions trips.

    Returns a LoopOutcome with classified outcome and full audit trail.
    """
    if max_iterations < 0:
        raise LoopError("max_iterations must be >= 0")
    if stuck_threshold < 2:
        raise LoopError("stuck_threshold must be >= 2 (1 fingerprint cannot be a repeat)")
    if base_cooldown_s < 0 or max_cooldown_s < 0:
        raise LoopError("cooldowns must be >= 0")
    if max_cooldown_s < base_cooldown_s:
        raise LoopError("max_cooldown_s must be >= base_cooldown_s")

    import time as _time
    if now is None:
        now = _time.monotonic
    if sleep is None:
        sleep = _time.sleep

    state = initial_state
    fingerprints: list[str] = []
    consecutive_no_progress = 0
    cooldowns_applied = 0
    total_cooldown_s = 0.0

    if max_iterations == 0:
        return LoopOutcome(outcome="exhausted", iterations=0, final_state=state, fingerprints=[])

    for i in range(1, max_iterations + 1):
        # Deadline check happens BEFORE the step so a tight deadline does not
        # charge the caller for one more LLM call after the budget is gone.
        if deadline_at is not None and now() >= deadline_at:
            return LoopOutcome(
                outcome="expired",
                iterations=i - 1,
                final_state=state,
                cooldowns_applied=cooldowns_applied,
                total_cooldown_s=total_cooldown_s,
                fingerprints=fingerprints,
            )

        # Apply cooldown if we've been spinning. Sleep BEFORE the step so the
        # caller pays wall-clock instead of model tokens.
        if consecutive_no_progress >= cooldown_after and base_cooldown_s > 0:
            n = consecutive_no_progress - cooldown_after
            wait = min(base_cooldown_s * (2 ** n), max_cooldown_s)
            sleep(wait)
            cooldowns_applied += 1
            total_cooldown_s += wait

        result = step(state)
        if not isinstance(result, StepResult):
            raise LoopError(f"step() must return StepResult, got {type(result).__name__}")
        state = result.state

        if result.done:
            return LoopOutcome(
                outcome="done",
                iterations=i,
                final_state=state,
                cooldowns_applied=cooldowns_applied,
                total_cooldown_s=total_cooldown_s,
                fingerprints=fingerprints,
            )

        try:
            fp = fingerprint(state)
        except Exception as e:
            raise LoopError(f"fingerprint() raised on iteration {i}: {e}") from e
        if not isinstance(fp, str):
            raise LoopError(f"fingerprint() must return str, got {type(fp).__name__}")
        fingerprints.append(fp)

        # Stuck detection: are the trailing `stuck_threshold` fingerprints all equal?
        if len(fingerprints) >= stuck_threshold and len(set(fingerprints[-stuck_threshold:])) == 1:
            return LoopOutcome(
                outcome="stuck",
                iterations=i,
                final_state=state,
                cooldowns_applied=cooldowns_applied,
                total_cooldown_s=total_cooldown_s,
                stuck_fingerprint=fp,
                fingerprints=fingerprints,
            )

        # No-progress = same fingerprint as previous iteration (the input to cooldown).
        if len(fingerprints) >= 2 and fingerprints[-1] == fingerprints[-2]:
            consecutive_no_progress += 1
        else:
            consecutive_no_progress = 0

    return LoopOutcome(
        outcome="exhausted",
        iterations=max_iterations,
        final_state=state,
        cooldowns_applied=cooldowns_applied,
        total_cooldown_s=total_cooldown_s,
        fingerprints=fingerprints,
    )

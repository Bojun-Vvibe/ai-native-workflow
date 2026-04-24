"""Pure exponential-backoff-with-jitter delay planner.

No I/O. No `time.sleep`. The planner returns the delay (seconds) the
caller should wait before the next attempt; the caller owns the actual
sleeping and the actual call. This split is what makes the policy
testable: a deterministic `Random` instance threaded through the
planner produces byte-stable plans across runs.

Three jitter strategies are supported, matching the AWS architecture
blog's canonical naming so policies are unambiguous in code review:

  - "none"        : delay = min(cap, base * 2**attempt)
  - "full"        : delay = uniform(0, min(cap, base * 2**attempt))
  - "equal"       : half-fixed, half-jittered
                    half = min(cap, base * 2**attempt) / 2
                    delay = half + uniform(0, half)
  - "decorrelated": delay = min(cap, uniform(base, prev_delay * 3))
                    (prev_delay starts at `base`)

The planner is a *plan*, not a loop: `plan(attempts_total)` returns the
full ordered list of `[ (attempt_index, delay_s), ... ]` so a test can
assert the entire schedule, and a caller can short-circuit on a
`Deadline` (compose with `templates/deadline-propagation`) by walking
the plan and stopping when the cumulative delay would exceed the
remaining budget.

`attempt_index` is 0-based and counts *retries*, not the original call.
A `attempts_total=4` plan therefore returns 3 entries: one delay
before retry #1, one before retry #2, one before retry #3.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import List, Tuple


class BackoffConfigError(ValueError):
    """Raised on a structurally invalid policy."""


_JITTER_KINDS = ("none", "full", "equal", "decorrelated")


@dataclass(frozen=True)
class BackoffPolicy:
    base_s: float
    cap_s: float
    jitter: str  # one of _JITTER_KINDS

    def __post_init__(self) -> None:
        if self.base_s <= 0:
            raise BackoffConfigError("base_s must be > 0")
        if self.cap_s < self.base_s:
            raise BackoffConfigError("cap_s must be >= base_s")
        if self.jitter not in _JITTER_KINDS:
            raise BackoffConfigError(
                f"jitter must be one of {_JITTER_KINDS}, got {self.jitter!r}"
            )


def plan(
    policy: BackoffPolicy,
    attempts_total: int,
    rng: Random,
) -> List[Tuple[int, float]]:
    """Return [(attempt_index, delay_s), ...] for retries 1..attempts_total-1.

    `attempts_total` is the *total* number of attempts including the
    original. A value of 1 means "no retries"; the returned list is
    empty. A value of `n` returns `n - 1` delays.
    """
    if attempts_total < 1:
        raise BackoffConfigError("attempts_total must be >= 1")
    out: List[Tuple[int, float]] = []
    prev_delay = policy.base_s
    for attempt_index in range(attempts_total - 1):
        ceiling = min(policy.cap_s, policy.base_s * (2 ** attempt_index))
        if policy.jitter == "none":
            delay = ceiling
        elif policy.jitter == "full":
            delay = rng.uniform(0.0, ceiling)
        elif policy.jitter == "equal":
            half = ceiling / 2.0
            delay = half + rng.uniform(0.0, half)
        elif policy.jitter == "decorrelated":
            upper = min(policy.cap_s, prev_delay * 3.0)
            # uniform(base, upper); upper >= base by construction
            delay = rng.uniform(policy.base_s, upper)
        else:  # pragma: no cover -- guarded in __post_init__
            raise BackoffConfigError(policy.jitter)
        prev_delay = delay
        out.append((attempt_index, delay))
    return out


def truncate_to_budget(
    schedule: List[Tuple[int, float]],
    budget_s: float,
) -> List[Tuple[int, float]]:
    """Walk a plan, keep delays whose cumulative sum stays <= budget_s.

    Useful when composing with a `Deadline`: the caller computes
    `remaining_s` and passes it in to drop trailing retries that cannot
    fit. Never reorders or scales delays — drops are tail-only so the
    surviving plan is still a valid prefix of the original.
    """
    if budget_s < 0:
        raise BackoffConfigError("budget_s must be >= 0")
    out: List[Tuple[int, float]] = []
    cumulative = 0.0
    for idx, d in schedule:
        if cumulative + d > budget_s:
            break
        out.append((idx, d))
        cumulative += d
    return out

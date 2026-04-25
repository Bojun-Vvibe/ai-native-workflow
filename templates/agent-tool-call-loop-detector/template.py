"""Agent tool-call loop detector.

Detects when an autonomous agent is stuck in a degenerate loop by inspecting
the recent tool-call history. Three signals are checked:

1. EXACT_REPEAT: the same (tool_name, canonical_args) tuple has appeared
   `repeat_threshold` times in the last `window` calls.
2. ABAB_CYCLE: an alternating two-call cycle (A,B,A,B,...) of length
   >= `cycle_min_len` in the tail.
3. NO_PROGRESS: the last `window` calls have produced no new
   distinct (tool_name, canonical_args) pair beyond the first.

The detector is pure / stdlib only and is meant to run inside the agent
host loop, *before* dispatching the next tool call. If a loop is detected,
the host should break out, escalate, or inject a corrective system message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable


def canonical_args(args: Any) -> str:
    """Stable JSON encoding of tool args so equal calls hash equal."""
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: Any  # any JSON-serializable structure

    def key(self) -> str:
        return f"{self.tool}::{canonical_args(self.args)}"


@dataclass
class LoopReport:
    looped: bool
    reason: str = ""
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"looped": self.looped, "reason": self.reason, "detail": self.detail}


def detect_loop(
    history: Iterable[ToolCall],
    *,
    window: int = 8,
    repeat_threshold: int = 3,
    cycle_min_len: int = 4,
) -> LoopReport:
    """Inspect the last `window` calls and decide if the agent is looping.

    Returns a LoopReport. `looped=False` means the host should proceed.
    """
    calls = list(history)[-window:]
    if len(calls) < repeat_threshold:
        return LoopReport(False, "insufficient_history", {"have": len(calls)})

    keys = [c.key() for c in calls]

    # Signal 1: exact repeat of the same call
    counts: dict[str, int] = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    worst_key, worst_count = max(counts.items(), key=lambda kv: kv[1])
    if worst_count >= repeat_threshold:
        return LoopReport(
            True,
            "exact_repeat",
            {"call": worst_key, "count": worst_count, "window": window},
        )

    # Signal 2: ABAB cycle in the tail
    if len(keys) >= cycle_min_len:
        tail = keys[-cycle_min_len:]
        a, b = tail[0], tail[1]
        if a != b and all(tail[i] == (a if i % 2 == 0 else b) for i in range(cycle_min_len)):
            return LoopReport(
                True,
                "abab_cycle",
                {"a": a, "b": b, "length": cycle_min_len},
            )

    # Signal 3: no progress (only one distinct call across the window)
    distinct = set(keys)
    if len(distinct) == 1 and len(keys) >= repeat_threshold:
        return LoopReport(
            True,
            "no_progress",
            {"call": next(iter(distinct)), "window": len(keys)},
        )

    return LoopReport(False, "ok", {"distinct": len(distinct), "window": len(keys)})

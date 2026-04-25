"""agent-tool-call-timestamp-monotonicity-validator

Pure stdlib validator that scans an agent's tool-call trace for
timestamp anomalies that silently corrupt downstream analysis.

The failure mode it catches: a trace is replayed, merged across
worker threads, or stitched together from multiple log shards, and
the timestamps end up out of order. Most analytics tools (latency
histograms, span trees, retry-rate dashboards) *render* such a trace
without warning — the bug is invisible until someone notices that
"this tool call apparently took -8 seconds."

Five findings:

- `non_monotonic` — within a single `(thread)`, two consecutive calls
  have `t[i] < t[i-1]`. The classic out-of-order replay bug.
- `duplicate_timestamp` — within a single thread, two calls share
  the exact same timestamp. Catches log-line merges where two events
  collapsed into one millisecond bucket and the ordering is now
  ambiguous.
- `clock_jump_forward` — within a single thread, a positive gap
  larger than `max_gap_ms` between consecutive calls. Catches NTP
  steps and laptop-sleep resumes where the agent was paused but the
  trace makes it look like the call took 47 minutes.
- `negative_duration` — a single call has `end_ms < start_ms`.
  Always a bug; impossible in real time.
- `future_timestamp` — a call's `end_ms` is greater than the
  caller-supplied `now_ms`. Catches workers writing with a clock
  drifted ahead of the orchestrator.

Per-thread grouping is the key design choice: a multi-threaded agent
*will* legitimately interleave timestamps in the global stream, and
flagging that as out-of-order would produce a deluge of false
positives. The validator only complains when ordering breaks
*within a single thread*, which is the only case that's actually a
bug.

Stdlib only. Pure function over an in-memory list. Findings sorted
by `(kind, thread, idx)` so two runs over the same input produce
byte-identical output (cron-friendly diffing).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict


class TimestampValidationError(ValueError):
    """Raised eagerly on malformed input."""


@dataclass(frozen=True)
class Finding:
    kind: str       # one of: non_monotonic, duplicate_timestamp,
                    # clock_jump_forward, negative_duration,
                    # future_timestamp
    thread: str
    idx: int        # 0-indexed position within the thread's call list
    detail: str


@dataclass
class MonotonicityReport:
    ok: bool
    per_thread: Dict[str, Dict[str, float]] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "per_thread": self.per_thread,
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            sort_keys=True,
        )


def _validate_call(c) -> None:
    if not isinstance(c, dict):
        raise TimestampValidationError(
            f"call must be dict, got {type(c).__name__}"
        )
    for k in ("thread", "tool", "start_ms", "end_ms"):
        if k not in c:
            raise TimestampValidationError(f"call missing key: {k!r}")
    if not isinstance(c["thread"], str) or not c["thread"]:
        raise TimestampValidationError("call.thread must be non-empty str")
    if not isinstance(c["tool"], str) or not c["tool"]:
        raise TimestampValidationError("call.tool must be non-empty str")
    for k in ("start_ms", "end_ms"):
        v = c[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise TimestampValidationError(
                f"call.{k} must be number, got {v!r}"
            )


def check(
    calls: list,
    *,
    now_ms: int | None = None,
    max_gap_ms: int = 60_000,
) -> MonotonicityReport:
    """Audit timestamp monotonicity across a list of tool calls.

    Args:
        calls: ordered list of `{thread, tool, start_ms, end_ms}`
            dicts. The list may be in any global order — per-thread
            order is what's audited.
        now_ms: optional caller's current timestamp. If supplied,
            calls with `end_ms > now_ms` fire `future_timestamp`.
        max_gap_ms: maximum acceptable positive gap between
            consecutive `start_ms` values within a thread before
            firing `clock_jump_forward`. Default 60s.

    Returns:
        MonotonicityReport with `ok=False` iff any finding fires.
    """
    if not isinstance(calls, list):
        raise TimestampValidationError(
            f"calls must be list, got {type(calls).__name__}"
        )
    for c in calls:
        _validate_call(c)

    # group by thread, preserve original insertion order
    threads: Dict[str, List[dict]] = {}
    order: List[str] = []
    for c in calls:
        t = c["thread"]
        if t not in threads:
            threads[t] = []
            order.append(t)
        threads[t].append(c)

    findings: List[Finding] = []
    per_thread: Dict[str, Dict[str, float]] = {}

    for t in order:
        group = threads[t]
        per_thread[t] = {
            "calls": float(len(group)),
            "first_start_ms": float(group[0]["start_ms"]),
            "last_end_ms": float(group[-1]["end_ms"]),
        }

        for i, c in enumerate(group):
            # negative_duration: per-call sanity
            if c["end_ms"] < c["start_ms"]:
                findings.append(
                    Finding(
                        "negative_duration",
                        t,
                        i,
                        f"end_ms {c['end_ms']} < start_ms {c['start_ms']} (tool={c['tool']})",
                    )
                )

            # future_timestamp: vs caller now
            if now_ms is not None and c["end_ms"] > now_ms:
                findings.append(
                    Finding(
                        "future_timestamp",
                        t,
                        i,
                        f"end_ms {c['end_ms']} > now_ms {now_ms} (tool={c['tool']})",
                    )
                )

            # cross-call (within thread) checks need a previous element
            if i == 0:
                continue
            prev = group[i - 1]
            if c["start_ms"] < prev["start_ms"]:
                findings.append(
                    Finding(
                        "non_monotonic",
                        t,
                        i,
                        f"start_ms {c['start_ms']} < previous {prev['start_ms']} (tool={c['tool']})",
                    )
                )
            elif c["start_ms"] == prev["start_ms"]:
                findings.append(
                    Finding(
                        "duplicate_timestamp",
                        t,
                        i,
                        f"start_ms {c['start_ms']} duplicates previous (tool={c['tool']})",
                    )
                )
            else:
                gap = c["start_ms"] - prev["start_ms"]
                if gap > max_gap_ms:
                    findings.append(
                        Finding(
                            "clock_jump_forward",
                            t,
                            i,
                            f"gap {gap}ms > max_gap_ms {max_gap_ms} (tool={c['tool']})",
                        )
                    )

    findings.sort(key=lambda f: (f.kind, f.thread, f.idx, f.detail))
    return MonotonicityReport(ok=not findings, per_thread=per_thread, findings=findings)


# ---------------------------------------------------------------------------
# Worked example
# ---------------------------------------------------------------------------

def _mk(thread, tool, start, end):
    return {"thread": thread, "tool": tool, "start_ms": start, "end_ms": end}


_CASES = [
    (
        "01_clean_single_thread",
        # Honest monotonic progression
        [
            _mk("T1", "read", 1000, 1010),
            _mk("T1", "edit", 1020, 1050),
            _mk("T1", "bash", 1100, 1300),
        ],
        2_000,  # now_ms
    ),
    (
        "02_clean_interleaved_threads",
        # Two threads interleaved in global order — must pass
        [
            _mk("T1", "read", 1000, 1010),
            _mk("T2", "grep", 1005, 1100),  # earlier than T1's next, but different thread
            _mk("T1", "edit", 1020, 1050),
            _mk("T2", "edit", 1200, 1300),
        ],
        2_000,
    ),
    (
        "03_non_monotonic",
        # Within T1, second call's start is BEFORE the first
        [
            _mk("T1", "read", 1000, 1010),
            _mk("T1", "edit", 900, 950),
            _mk("T1", "bash", 1100, 1300),
        ],
        2_000,
    ),
    (
        "04_duplicate_timestamp",
        [
            _mk("T1", "read", 1000, 1010),
            _mk("T1", "edit", 1000, 1050),  # same start as previous
        ],
        2_000,
    ),
    (
        "05_clock_jump",
        # 90-second positive gap on the same thread — laptop sleep
        [
            _mk("T1", "read", 1_000, 1_100),
            _mk("T1", "bash", 91_000, 91_500),
        ],
        100_000,
    ),
    (
        "06_negative_duration",
        [
            _mk("T1", "broken", 5_000, 4_000),
        ],
        10_000,
    ),
    (
        "07_future_timestamp",
        [
            _mk("T1", "drifted", 1_000, 9_999),
        ],
        5_000,  # call ended in the future relative to now
    ),
    (
        "08_combined",
        # All three intra-thread bugs at once on the same thread
        [
            _mk("T1", "a", 1_000, 1_100),
            _mk("T1", "b", 1_000, 1_200),  # duplicate_timestamp
            _mk("T1", "c", 800, 900),      # non_monotonic
            _mk("T1", "d", 70_000, 70_500),  # clock_jump_forward (vs c=800)
        ],
        100_000,
    ),
]


def _run_demo() -> None:
    print("# agent-tool-call-timestamp-monotonicity-validator — worked example")
    print()
    for name, calls, now_ms in _CASES:
        print(f"## case {name}")
        print(f"calls: {len(calls)}  now_ms: {now_ms}")
        result = check(calls, now_ms=now_ms)
        print(result.to_json())
        print()


if __name__ == "__main__":
    _run_demo()

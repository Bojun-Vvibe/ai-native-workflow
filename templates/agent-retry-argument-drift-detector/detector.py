"""Detect argument drift across retry attempts of the same tool call.

When an agent retries a tool call (after a transient failure, timeout, or rate limit)
the *arguments* must be byte-identical to the original attempt — otherwise the retry
is not a retry, it is a *different* call sharing an attempt-id. This is the silent
source of:

  * double-charge bugs (`pay(amount=100)` retried as `pay(amount=100.0)` → two charges
    if the idempotency key was derived from the canonical-args hash)
  * "ghost edits" (`write_file(path="/a", content="v1")` retried as `path="/a", content="v2"`
    after the orchestrator's planner ran one more step between the throw and the catch)
  * stale-cache reads that the cache layer cannot see because the keys differ by one
    whitespace character

This detector is the read side of `tool-call-idempotency-key`: that template guarantees
*if* the args match *then* the call is deduped; this template *verifies* the args
actually match across attempts and flags the cases where they do not.

Pure stdlib, pure function over an in-memory list of attempts, no I/O, no clocks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class DriftValidationError(Exception):
    """Raised when input is structurally broken (cannot meaningfully be analyzed)."""


@dataclass(frozen=True)
class Attempt:
    """One attempt of one tool call."""

    call_id: str  # logical idempotency id — every attempt of one call shares this
    attempt_no: int  # 1, 2, 3, ... within one call_id
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class DriftFinding:
    call_id: str
    kind: str  # one of: "tool_changed", "key_added", "key_removed", "value_changed",
    #               "type_changed", "duplicate_attempt_no", "non_dense_attempt_no"
    detail: str  # human-readable, includes JSON pointer when applicable


@dataclass
class DriftReport:
    findings: list[DriftFinding] = field(default_factory=list)
    calls_checked: int = 0
    attempts_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings


def _canonical(value: Any) -> str:
    """Stable JSON for one argument value. Sorted keys, no whitespace.

    Floats are allowed but normalized through json (no NaN/Infinity — we want a
    finding, not a crash). The point is byte-stability across retries, so anything
    json.dumps will accept is fine.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _hash_args(args: dict[str, Any]) -> str:
    blob = _canonical(args).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _typename(v: Any) -> str:
    # We treat int and float as distinct (the ghost-edit `100` vs `100.0` case)
    # but bool as bool (not int) because Python's bool-is-int is a footgun here.
    if isinstance(v, bool):
        return "bool"
    return type(v).__name__


def detect(attempts: list[Attempt]) -> DriftReport:
    """Group attempts by call_id, walk each group in attempt_no order, diff args.

    Returns a sorted report. Pure: no clocks, no I/O.
    """
    report = DriftReport()
    if not attempts:
        return report

    # Group by call_id.
    by_call: dict[str, list[Attempt]] = {}
    for a in attempts:
        if not a.call_id:
            raise DriftValidationError("empty call_id")
        if a.attempt_no < 1:
            raise DriftValidationError(f"attempt_no must be >= 1, got {a.attempt_no} for call_id={a.call_id}")
        by_call.setdefault(a.call_id, []).append(a)

    for call_id in sorted(by_call):
        group = by_call[call_id]
        report.calls_checked += 1
        report.attempts_checked += len(group)

        # Sort by attempt_no for deterministic walking.
        group_sorted = sorted(group, key=lambda x: x.attempt_no)

        # Check density and uniqueness of attempt_no.
        seen_nos: set[int] = set()
        for a in group_sorted:
            if a.attempt_no in seen_nos:
                report.findings.append(
                    DriftFinding(call_id, "duplicate_attempt_no", f"attempt_no={a.attempt_no} appears twice")
                )
            seen_nos.add(a.attempt_no)
        # Dense from 1 (a missing #2 means we cannot trust the diff between #1 and #3 — log it).
        expected = set(range(1, len(group_sorted) + 1))
        missing = expected - seen_nos
        if missing:
            report.findings.append(
                DriftFinding(
                    call_id,
                    "non_dense_attempt_no",
                    f"missing attempt_no(s): {sorted(missing)}",
                )
            )

        # Diff each attempt against the first attempt (the canonical "what we meant to do").
        first = group_sorted[0]
        for a in group_sorted[1:]:
            if a.tool != first.tool:
                report.findings.append(
                    DriftFinding(
                        call_id,
                        "tool_changed",
                        f"attempt {a.attempt_no}: tool={a.tool!r} (first attempt used {first.tool!r})",
                    )
                )
                # Keep going — arg diff is still useful information for the operator.
            first_keys = set(first.args.keys())
            this_keys = set(a.args.keys())
            for k in sorted(this_keys - first_keys):
                report.findings.append(
                    DriftFinding(call_id, "key_added", f"attempt {a.attempt_no}: arg /{k} added (was absent at attempt 1)")
                )
            for k in sorted(first_keys - this_keys):
                report.findings.append(
                    DriftFinding(call_id, "key_removed", f"attempt {a.attempt_no}: arg /{k} removed (was present at attempt 1)")
                )
            for k in sorted(first_keys & this_keys):
                v_first = first.args[k]
                v_this = a.args[k]
                t_first = _typename(v_first)
                t_this = _typename(v_this)
                if t_first != t_this:
                    report.findings.append(
                        DriftFinding(
                            call_id,
                            "type_changed",
                            f"attempt {a.attempt_no}: arg /{k} type {t_first}->{t_this} "
                            f"(first={v_first!r}, this={v_this!r})",
                        )
                    )
                    continue
                # Same type — compare canonically.
                if _canonical(v_first) != _canonical(v_this):
                    report.findings.append(
                        DriftFinding(
                            call_id,
                            "value_changed",
                            f"attempt {a.attempt_no}: arg /{k} value drifted "
                            f"(first={_canonical(v_first)}, this={_canonical(v_this)})",
                        )
                    )

    # Stable sort: (call_id, kind, detail) so two runs over same input produce identical output.
    report.findings.sort(key=lambda f: (f.call_id, f.kind, f.detail))
    return report


def fingerprint_attempt(a: Attempt) -> str:
    """Operator helper: short hash of (tool, canonical args).

    Two attempts with the same fingerprint are byte-identical retries; different
    fingerprints inside one call_id is the bug this template catches.
    """
    blob = f"{a.tool}|{_canonical(a.args)}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]

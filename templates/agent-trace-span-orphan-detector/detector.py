"""
agent-trace-span-orphan-detector
================================

Pure stdlib detector for structural anomalies in an agent execution trace
expressed as a list of spans. Each span is a dict with at least:

  {
    "span_id":        "<unique non-empty str>",
    "parent_span_id": "<span_id of parent, or None for the root>",
    "trace_id":       "<unique non-empty str>",
    "name":           "<human-readable label>",
    "started_at":     <unix seconds, float or int>,
    "finished_at":    <unix seconds, float or int>  # optional; None = still open
  }

Catches four classes of structural bug that silently corrupt downstream
trace analysis (Honeycomb / Tempo / Jaeger UIs all *render* a broken trace
without warning, so the operator sees a tidy tree that is missing branches):

  - orphan          : parent_span_id refers to a span_id not in the trace
  - multiple_roots  : more than one span has parent_span_id=None
  - cycle           : following parent_span_id chains hits a span twice
  - cross_trace     : a span's parent lives in a *different* trace_id

Plus a soft `dangling_open` warning (span has no finished_at and is not
the most recent activity) so a forgotten `span.end()` is visible.

Hard rule: this is a *pure* function over an in-memory list. No I/O, no
clocks, no transport. Caller decides whether to fail CI, drop the trace,
or annotate-and-keep.

Returns a structured TraceReport so the host can emit one decision-log
line per finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TraceValidationError(ValueError):
    """Raised on malformed input (missing required field, wrong type)."""


@dataclass(frozen=True)
class Finding:
    kind: str                # orphan | multiple_roots | cycle | cross_trace | dangling_open
    span_id: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "span_id": self.span_id, "detail": self.detail}


@dataclass(frozen=True)
class TraceReport:
    ok: bool
    span_count: int
    root_count: int
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "span_count": self.span_count,
            "root_count": self.root_count,
            "findings": [f.to_dict() for f in self.findings],
        }


_REQUIRED_FIELDS = ("span_id", "parent_span_id", "trace_id", "name", "started_at")


def _validate_span(span: Any, idx: int) -> None:
    if not isinstance(span, dict):
        raise TraceValidationError(f"span[{idx}] is not a dict")
    for fname in _REQUIRED_FIELDS:
        if fname not in span:
            raise TraceValidationError(f"span[{idx}] missing required field {fname!r}")
    if not isinstance(span["span_id"], str) or not span["span_id"]:
        raise TraceValidationError(f"span[{idx}].span_id must be non-empty str")
    if span["parent_span_id"] is not None and not (
        isinstance(span["parent_span_id"], str) and span["parent_span_id"]
    ):
        raise TraceValidationError(
            f"span[{idx}].parent_span_id must be None or non-empty str"
        )
    if not isinstance(span["trace_id"], str) or not span["trace_id"]:
        raise TraceValidationError(f"span[{idx}].trace_id must be non-empty str")
    if not isinstance(span["started_at"], (int, float)):
        raise TraceValidationError(f"span[{idx}].started_at must be number")


def detect(spans: list[dict[str, Any]]) -> TraceReport:
    """
    Inspect a list of spans for structural anomalies. Pure function.

    The input list is treated as immutable; no fields are mutated.
    Findings are deterministic — sorted by (kind, span_id) so two runs over
    the same input produce byte-identical output (cron-friendly diffing).
    """
    if not isinstance(spans, list):
        raise TraceValidationError("spans must be a list")
    for i, s in enumerate(spans):
        _validate_span(s, i)

    # Detect duplicate span_id eagerly — this is *its own* corruption class
    # and would make the rest of the analysis ambiguous.
    seen_ids: set[str] = set()
    for i, s in enumerate(spans):
        if s["span_id"] in seen_ids:
            raise TraceValidationError(
                f"span[{i}].span_id={s['span_id']!r} is duplicated in input"
            )
        seen_ids.add(s["span_id"])

    by_id: dict[str, dict[str, Any]] = {s["span_id"]: s for s in spans}
    findings: list[Finding] = []

    # 1. multiple_roots — scoped *per trace_id* (a span batch may legitimately
    # span more than one trace; the rule is one root per trace_id).
    roots = [s for s in spans if s["parent_span_id"] is None]
    roots_by_trace: dict[str, list[dict[str, Any]]] = {}
    for r in roots:
        roots_by_trace.setdefault(r["trace_id"], []).append(r)
    for tid, rs in roots_by_trace.items():
        if len(rs) > 1:
            for r in rs:
                findings.append(
                    Finding(
                        kind="multiple_roots",
                        span_id=r["span_id"],
                        detail=(
                            f"trace_id={tid!r} has {len(rs)} roots; "
                            "expected exactly 1"
                        ),
                    )
                )

    # 2. orphan + cross_trace + cycle (per-span pass)
    for s in spans:
        pid = s["parent_span_id"]
        if pid is None:
            continue
        parent = by_id.get(pid)
        if parent is None:
            findings.append(
                Finding(
                    kind="orphan",
                    span_id=s["span_id"],
                    detail=f"parent_span_id={pid!r} not present in trace",
                )
            )
            continue
        if parent["trace_id"] != s["trace_id"]:
            findings.append(
                Finding(
                    kind="cross_trace",
                    span_id=s["span_id"],
                    detail=(
                        f"trace_id={s['trace_id']!r} but parent={pid!r} "
                        f"has trace_id={parent['trace_id']!r}"
                    ),
                )
            )

        # cycle detection: walk parent chain, bound by span count
        cur = s
        seen_in_walk: set[str] = set()
        steps = 0
        while cur is not None:
            if cur["span_id"] in seen_in_walk:
                findings.append(
                    Finding(
                        kind="cycle",
                        span_id=s["span_id"],
                        detail=f"parent chain loops at {cur['span_id']!r}",
                    )
                )
                break
            seen_in_walk.add(cur["span_id"])
            ppid = cur["parent_span_id"]
            if ppid is None:
                break
            cur = by_id.get(ppid)
            steps += 1
            if steps > len(spans):
                # safety net — shouldn't trigger if cycle logic above is right
                findings.append(
                    Finding(
                        kind="cycle",
                        span_id=s["span_id"],
                        detail="parent chain exceeded span count without root",
                    )
                )
                break

    # 3. dangling_open: a span without finished_at AND it's not the latest start
    if spans:
        latest_start = max(s["started_at"] for s in spans)
        for s in spans:
            if s.get("finished_at") is None and s["started_at"] != latest_start:
                findings.append(
                    Finding(
                        kind="dangling_open",
                        span_id=s["span_id"],
                        detail="span has no finished_at and is not the latest activity",
                    )
                )

    findings.sort(key=lambda f: (f.kind, f.span_id))

    # ok=True iff zero hard findings; dangling_open is a soft warning that
    # still flips ok=False because forgetting to close a span breaks duration math.
    return TraceReport(
        ok=len(findings) == 0,
        span_count=len(spans),
        root_count=len(roots),
        findings=tuple(findings),
    )

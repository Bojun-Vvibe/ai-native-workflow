#!/usr/bin/env python3
"""Agent checkpoint + resume engine.

Append-only JSONL checkpoint format that lets a long-running agent
mission survive crash, preemption, or kill-9 without re-doing work.

Two record types per step:

    {"kind":"step_begin", "step_id":..., "step_index":N, "ts":...,
     "input_hash":..., "tools_planned":[...]}
    {"kind":"step_end",   "step_id":..., "step_index":N, "ts":...,
     "output_hash":..., "tools_called":[...], "exit_state":"continue"|"done"|...}

A step is *committed* only when its `step_end` is fsynced. On resume:

  1. Load the JSONL.
  2. Pair `step_begin` / `step_end` records by `step_id`.
  3. Find the highest `step_index` with a matching `step_end` whose
     `input_hash` equals the planner's recomputed hash for that step.
  4. Replay context (= concatenation of committed step outputs) and
     start from `step_index + 1`.

The mismatch case matters: if the planner now produces a different
`input_hash` for an already-committed step (because the prompt, model,
or earlier outputs drifted), the resume engine MUST refuse to fast-forward
past it. We surface `resume_state="invalidated"` with the offending
step_id so the operator can decide: rerun from there, force-accept,
or abort.

Determinism: hashing is over canonical-JSON SHA-256. Same inputs
always produce the same hash; reordered keys do not.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def canonical_hash(obj: Any) -> str:
    """Stable SHA-256 over canonical JSON. Keys sorted, no whitespace."""
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class StepRecord:
    step_id: str
    step_index: int
    input_hash: str
    output_hash: str | None
    tools_planned: list[str]
    tools_called: list[str]
    exit_state: str | None
    begin_ts: int
    end_ts: int | None

    @property
    def committed(self) -> bool:
        return self.output_hash is not None and self.exit_state is not None


@dataclass
class ResumePlan:
    state: str  # "fresh" | "resume" | "invalidated" | "complete"
    next_step_index: int
    committed_steps: list[StepRecord] = field(default_factory=list)
    invalidated_step_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "state": self.state,
            "next_step_index": self.next_step_index,
            "committed_count": len(self.committed_steps),
        }
        if self.invalidated_step_id is not None:
            out["invalidated_step_id"] = self.invalidated_step_id
        if self.detail:
            out["detail"] = self.detail
        return out


def load_checkpoint(path: str) -> list[StepRecord]:
    """Pair begin/end records by step_id. Returns records ordered by step_index."""
    by_id: dict[str, dict[str, Any]] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            evt = json.loads(line)
            sid = evt["step_id"]
            slot = by_id.setdefault(sid, {})
            slot[evt["kind"]] = evt
    records: list[StepRecord] = []
    for sid, slot in by_id.items():
        b = slot.get("step_begin")
        if b is None:
            # An end without a begin is corrupt input; skip with no crash.
            continue
        e = slot.get("step_end")
        records.append(StepRecord(
            step_id=sid,
            step_index=b["step_index"],
            input_hash=b["input_hash"],
            output_hash=(e["output_hash"] if e else None),
            tools_planned=b.get("tools_planned", []),
            tools_called=(e.get("tools_called", []) if e else []),
            exit_state=(e.get("exit_state") if e else None),
            begin_ts=b["ts"],
            end_ts=(e["ts"] if e else None),
        ))
    records.sort(key=lambda r: r.step_index)
    return records


def plan_resume(records: list[StepRecord],
                expected_input_hashes: dict[int, str]) -> ResumePlan:
    """Decide where to resume from.

    `expected_input_hashes` is `{step_index: hash}` recomputed by the
    planner for each step it would produce starting from index 0,
    given the *current* prompt+model+earlier-outputs. We walk
    committed records in index order; the first mismatch invalidates.
    """
    if not records:
        return ResumePlan("fresh", next_step_index=0)
    committed: list[StepRecord] = []
    for r in records:
        if not r.committed:
            # An uncommitted step means crash mid-step; resume from it.
            return ResumePlan("resume", next_step_index=r.step_index,
                              committed_steps=committed,
                              detail={"reason": "uncommitted_step",
                                      "step_id": r.step_id})
        expected = expected_input_hashes.get(r.step_index)
        if expected is None:
            # Planner now produces fewer steps; treat as invalidated.
            return ResumePlan("invalidated", next_step_index=r.step_index,
                              committed_steps=committed,
                              invalidated_step_id=r.step_id,
                              detail={"reason": "planner_truncated"})
        if expected != r.input_hash:
            return ResumePlan("invalidated", next_step_index=r.step_index,
                              committed_steps=committed,
                              invalidated_step_id=r.step_id,
                              detail={"reason": "input_hash_drift",
                                      "expected": expected,
                                      "found": r.input_hash})
        committed.append(r)
        if r.exit_state == "done":
            return ResumePlan("complete", next_step_index=r.step_index + 1,
                              committed_steps=committed)
    # All records committed cleanly, none was "done": resume at the next index.
    return ResumePlan("resume", next_step_index=committed[-1].step_index + 1,
                      committed_steps=committed,
                      detail={"reason": "tail_resume"})


def append_begin(path: str, *, step_id: str, step_index: int,
                 input_hash: str, tools_planned: list[str], ts: int) -> None:
    _append(path, {"kind": "step_begin", "step_id": step_id,
                   "step_index": step_index, "input_hash": input_hash,
                   "tools_planned": tools_planned, "ts": ts})


def append_end(path: str, *, step_id: str, step_index: int,
               output_hash: str, tools_called: list[str],
               exit_state: str, ts: int) -> None:
    _append(path, {"kind": "step_end", "step_id": step_id,
                   "step_index": step_index, "output_hash": output_hash,
                   "tools_called": tools_called, "exit_state": exit_state,
                   "ts": ts})


def _append(path: str, evt: dict[str, Any]) -> None:
    """Append + flush + fsync. Single-writer assumption."""
    import os
    line = json.dumps(evt, sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode())
        os.fsync(fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: checkpoint.py <log.jsonl> <expected_hashes.json>",
              file=sys.stderr)
        sys.exit(2)
    records = load_checkpoint(sys.argv[1])
    with open(sys.argv[2]) as f:
        raw = json.load(f)
    expected = {int(k): v for k, v in raw.items()}
    plan = plan_resume(records, expected)
    print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    sys.exit(0 if plan.state in ("fresh", "resume", "complete") else 1)

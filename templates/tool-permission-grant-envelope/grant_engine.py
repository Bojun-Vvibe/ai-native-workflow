#!/usr/bin/env python3
"""Tool-permission grant engine.

Deterministic, stdlib-only authorization decision for "is this agent
allowed to make this tool call right now?". Decoupled from cost
(`agent-cost-budget-envelope`), retry (`tool-call-retry-envelope`),
and health (`tool-call-circuit-breaker`).

A grant is a declarative statement of the form:

    agent X may call tool Y with scope subset S, up to N times,
    until time T, optionally restricted by argument predicates.

Decision precedence (deterministic, no order-dependence):
  1. Hard deny on missing/expired/revoked grant   -> deny(reason=no_grant|expired|revoked)
  2. Tool-name match                              -> deny(reason=tool_not_in_grant)
  3. Required scopes subset of granted scopes     -> deny(reason=scope_not_granted, missing=...)
  4. Argument predicates (allowlist match)        -> deny(reason=argument_not_allowed, field=..., value=...)
  5. Per-grant call counter < max_calls           -> deny(reason=call_quota_exhausted, used=N, max=N)
  6. otherwise                                    -> allow(remaining=...)

Important: rule (5) is checked LAST so that a quota-exhausted grant
on a tool the agent shouldn't be touching still reports the *real*
reason (tool_not_in_grant / scope_not_granted), not a misleading
"out of quota". This matches the same "specific reason wins" pattern
used in `agent-cost-budget-envelope`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Grant:
    grant_id: str
    agent_id: str
    tool: str
    scopes: tuple[str, ...]
    max_calls: int
    expires_at: int  # unix seconds; 0 = never
    arg_allow: dict[str, list[Any]] = field(default_factory=dict)
    revoked: bool = False


@dataclass
class CallRequest:
    agent_id: str
    tool: str
    required_scopes: tuple[str, ...]
    args: dict[str, Any]
    now: int  # unix seconds


@dataclass
class Decision:
    allowed: bool
    reason: str
    grant_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"allowed": self.allowed, "reason": self.reason}
        if self.grant_id is not None:
            out["grant_id"] = self.grant_id
        if self.detail:
            out["detail"] = self.detail
        return out


def _candidate_grants(grants: list[Grant], req: CallRequest) -> list[Grant]:
    """Grants belonging to this agent, sorted by grant_id for determinism."""
    return sorted(
        [g for g in grants if g.agent_id == req.agent_id],
        key=lambda g: g.grant_id,
    )


def decide(grants: list[Grant], usage: dict[str, int], req: CallRequest) -> Decision:
    """Return a Decision for `req` against the agent's grants.

    `usage` is `{grant_id: calls_used_so_far}` and is NOT mutated here;
    the caller increments it on `allowed=True`. This keeps the engine
    pure and replayable from a JSONL grant-event log.
    """
    candidates = _candidate_grants(grants, req)
    if not candidates:
        return Decision(False, "no_grant")

    # Pass 1: filter by tool, surfacing the most-specific reason.
    tool_matches = [g for g in candidates if g.tool == req.tool]
    if not tool_matches:
        return Decision(False, "tool_not_in_grant", detail={"tool": req.tool})

    # Pass 2: among tool-matching grants, find the first non-revoked,
    # non-expired one whose scopes + arg predicates pass. Quota check
    # happens last per docstring.
    last_specific: Decision | None = None
    for g in tool_matches:
        if g.revoked:
            last_specific = Decision(False, "revoked", grant_id=g.grant_id)
            continue
        if g.expires_at and req.now >= g.expires_at:
            last_specific = Decision(
                False, "expired", grant_id=g.grant_id,
                detail={"expires_at": g.expires_at, "now": req.now},
            )
            continue
        missing = [s for s in req.required_scopes if s not in g.scopes]
        if missing:
            last_specific = Decision(
                False, "scope_not_granted", grant_id=g.grant_id,
                detail={"missing": missing},
            )
            continue
        bad_arg = _check_args(g, req)
        if bad_arg is not None:
            field_, value = bad_arg
            last_specific = Decision(
                False, "argument_not_allowed", grant_id=g.grant_id,
                detail={"field": field_, "value": value},
            )
            continue
        used = usage.get(g.grant_id, 0)
        if used >= g.max_calls:
            last_specific = Decision(
                False, "call_quota_exhausted", grant_id=g.grant_id,
                detail={"used": used, "max": g.max_calls},
            )
            continue
        return Decision(
            True, "ok", grant_id=g.grant_id,
            detail={"remaining": g.max_calls - used - 1},
        )

    # No grant fully passed; surface the most-specific reason from the
    # last candidate that matched the tool.
    assert last_specific is not None
    return last_specific


def _check_args(g: Grant, req: CallRequest) -> tuple[str, Any] | None:
    for field_name, allowed_values in g.arg_allow.items():
        if field_name not in req.args:
            return (field_name, None)
        if req.args[field_name] not in allowed_values:
            return (field_name, req.args[field_name])
    return None


def load_grants(path: str) -> list[Grant]:
    """Load a grants.json file (a list of grant dicts)."""
    with open(path) as f:
        raw = json.load(f)
    return [Grant(**g) for g in raw]


def replay_log(grants: list[Grant], log_path: str) -> dict[str, int]:
    """Rebuild `usage` from a JSONL event log of allowed calls.

    Each line is `{"grant_id": "...", "ts": int}`. Lines for unknown
    grant_ids are ignored (a revoked-then-recreated grant is a new id).
    """
    known = {g.grant_id for g in grants}
    usage: dict[str, int] = {}
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            evt = json.loads(line)
            gid = evt.get("grant_id")
            if gid in known:
                usage[gid] = usage.get(gid, 0) + 1
    return usage


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print(
            "usage: grant_engine.py <grants.json> <events.jsonl> <request.json>",
            file=sys.stderr,
        )
        sys.exit(2)
    grants = load_grants(sys.argv[1])
    usage = replay_log(grants, sys.argv[2])
    with open(sys.argv[3]) as f:
        req_raw = json.load(f)
    req_raw["required_scopes"] = tuple(req_raw.get("required_scopes", []))
    req = CallRequest(**req_raw)
    decision = decide(grants, usage, req)
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    sys.exit(0 if decision.allowed else 1)

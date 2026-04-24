#!/usr/bin/env python3
"""Reference budget envelope: check() + record() against a JSONL ledger.

Stdlib only. See ENVELOPE.md for the full spec.

Usage as a module:
    from budget_envelope import load_policy, Ledger, Request, check, record

Usage as a CLI demo:
    budget_envelope.py demo <policy.json> <ledger.jsonl> <request.json>
        → prints the Decision as JSON; calls record() if allow/allow_degraded
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Request:
    session_id: str
    tier: str
    projected_input_tokens: int
    projected_output_tokens: int
    timestamp: str  # ISO 8601 UTC

    @classmethod
    def from_dict(cls, d: dict) -> "Request":
        return cls(
            session_id=d["session_id"],
            tier=d["tier"],
            projected_input_tokens=int(d["projected_input_tokens"]),
            projected_output_tokens=int(d["projected_output_tokens"]),
            timestamp=d["timestamp"],
        )


@dataclass
class Decision:
    decision: str  # allow | allow_degraded | deny
    tier: str
    projected_usd: float
    reason: str
    headroom_usd: float | None


@dataclass
class Response:
    session_id: str
    tier: str
    input_tokens: int
    output_tokens: int
    timestamp: str
    reason: str  # carried from the Decision


class Ledger:
    """In-memory ledger with optional JSONL persistence."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.rows: list[dict] = []
        if path and path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line:
                    self.rows.append(json.loads(line))

    def append(self, row: dict) -> None:
        self.rows.append(row)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")

    def session_total_usd(self, session_id: str) -> float:
        return round(sum(r["usd"] for r in self.rows if r["session_id"] == session_id), 6)

    def day_total_usd(self, ts_iso: str) -> float:
        day = _utc_day(ts_iso)
        return round(sum(r["usd"] for r in self.rows if _utc_day(r["ts"]) == day), 6)


def _utc_day(ts_iso: str) -> str:
    s = ts_iso.replace("Z", "+00:00")
    return datetime.fromisoformat(s).astimezone(timezone.utc).date().isoformat()


def load_policy(path: Path) -> dict:
    p = json.loads(Path(path).read_text())
    if p.get("version") != 1:
        raise ValueError(f"unsupported policy version: {p.get('version')!r}")
    if "default" not in p["tiers"]:
        raise ValueError("policy.tiers must include a 'default' tier")
    caps = p["caps"]
    if not (caps["per_day"]["usd"] >= caps["per_session"]["usd"] >= caps["per_call"]["usd"]):
        raise ValueError("caps must satisfy per_day >= per_session >= per_call")
    for name, c in caps.items():
        if c["on_trip"] not in ("degrade", "kill"):
            raise ValueError(f"caps.{name}.on_trip must be 'degrade' or 'kill'")
        if c["on_trip"] == "degrade":
            if "degrade_to" not in c:
                raise ValueError(f"caps.{name} on_trip=degrade requires degrade_to")
            if c["degrade_to"] not in p["tiers"]:
                raise ValueError(f"caps.{name}.degrade_to refers to unknown tier {c['degrade_to']!r}")
    return p


def project_usd(policy: dict, tier_name: str, in_tok: int, out_tok: int) -> float:
    t = policy["tiers"].get(tier_name)
    if t is None:
        raise KeyError(tier_name)
    return round((in_tok / 1000.0) * t["input_per_1k"] + (out_tok / 1000.0) * t["output_per_1k"], 6)


def _check_one_cap(
    cap_name: str,
    cap: dict,
    rollup_usd: float,
    projected_usd: float,
    current_tier: str,
    policy: dict,
    in_tok: int,
    out_tok: int,
    reason_code: str,
) -> tuple[str, str, float, str, float | None]:
    """Return (decision, tier, projected_usd, reason, headroom)."""
    headroom = round(cap["usd"] - rollup_usd, 6)
    if rollup_usd + projected_usd <= cap["usd"]:
        return ("allow", current_tier, projected_usd, "ok", None)
    if cap["on_trip"] == "degrade":
        new_tier = cap["degrade_to"]
        new_proj = project_usd(policy, new_tier, in_tok, out_tok)
        if rollup_usd + new_proj <= cap["usd"]:
            return ("allow_degraded", new_tier, new_proj, reason_code, headroom)
        return ("deny", new_tier, new_proj, reason_code, headroom)
    # kill
    return ("deny", current_tier, projected_usd, reason_code, headroom)


def check(policy: dict, ledger: Ledger, req: Request) -> Decision:
    # 1. kill switch
    ks = policy.get("kill_switch_usd_remaining")
    if ks is not None and ks <= 0.0:
        return Decision("deny", req.tier, 0.0, "kill_switch_engaged", 0.0)

    # 2. project at requested tier
    if req.tier not in policy["tiers"]:
        return Decision("deny", req.tier, 0.0, "unknown_tier", None)
    proj = project_usd(policy, req.tier, req.projected_input_tokens, req.projected_output_tokens)

    current_tier = req.tier
    current_proj = proj
    degrade_reason: str | None = None
    degrade_headroom: float | None = None

    # 3. per-call (rollup is 0 — single call)
    d, current_tier, current_proj, reason, headroom = _check_one_cap(
        "per_call", policy["caps"]["per_call"], 0.0, current_proj,
        current_tier, policy, req.projected_input_tokens, req.projected_output_tokens,
        "per_call_cap_exceeded",
    )
    if d == "deny":
        return Decision("deny", current_tier, current_proj, reason, headroom)
    if d == "allow_degraded":
        degrade_reason, degrade_headroom = reason, headroom

    # 4. per-session (rollup at the *current effective tier*)
    sess_rollup = ledger.session_total_usd(req.session_id)
    d, current_tier, current_proj, reason, headroom = _check_one_cap(
        "per_session", policy["caps"]["per_session"], sess_rollup, current_proj,
        current_tier, policy, req.projected_input_tokens, req.projected_output_tokens,
        "per_session_cap_exceeded",
    )
    if d == "deny":
        return Decision("deny", current_tier, current_proj, reason, headroom)
    if d == "allow_degraded":
        degrade_reason, degrade_headroom = reason, headroom

    # 5. per-day
    day_rollup = ledger.day_total_usd(req.timestamp)
    d, current_tier, current_proj, reason, headroom = _check_one_cap(
        "per_day", policy["caps"]["per_day"], day_rollup, current_proj,
        current_tier, policy, req.projected_input_tokens, req.projected_output_tokens,
        "per_day_cap_exceeded",
    )
    if d == "deny":
        return Decision("deny", current_tier, current_proj, reason, headroom)
    if d == "allow_degraded":
        degrade_reason, degrade_headroom = reason, headroom

    if degrade_reason is not None:
        return Decision("allow_degraded", current_tier, current_proj, degrade_reason, degrade_headroom)
    return Decision("allow", current_tier, current_proj, "ok", None)


def record(ledger: Ledger, resp: Response, usd_actual: float) -> None:
    ledger.append({
        "ts": resp.timestamp,
        "session_id": resp.session_id,
        "tier": resp.tier,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "usd": round(usd_actual, 6),
        "reason": resp.reason,
    })


def _demo(argv: list[str]) -> int:
    if len(argv) != 4 or argv[0] != "demo":
        print(__doc__, file=sys.stderr)
        return 1
    policy = load_policy(Path(argv[1]))
    ledger = Ledger(Path(argv[2]))
    req_d = json.loads(Path(argv[3]).read_text())
    req = Request.from_dict(req_d)
    dec = check(policy, ledger, req)
    print(json.dumps(asdict(dec), sort_keys=True, indent=2))
    if dec.decision in ("allow", "allow_degraded"):
        # Treat projections as actuals for the demo (real callers would pass response usage)
        resp = Response(
            session_id=req.session_id,
            tier=dec.tier,
            input_tokens=req.projected_input_tokens,
            output_tokens=req.projected_output_tokens,
            timestamp=req.timestamp,
            reason=dec.reason,
        )
        record(ledger, resp, dec.projected_usd)
    return 0


if __name__ == "__main__":
    sys.exit(_demo(sys.argv[1:]))

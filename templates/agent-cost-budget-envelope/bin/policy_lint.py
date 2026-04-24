#!/usr/bin/env python3
"""Lint a policy.json against the constraints in ENVELOPE.md.

Usage:
    policy_lint.py <policy.json>

Exit:
    0 — clean
    1 — at least one issue
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    p = json.loads(Path(argv[1]).read_text())
    issues: list[str] = []
    if p.get("version") != 1:
        issues.append(f"version must be 1, got {p.get('version')!r}")
    tiers = p.get("tiers", {})
    if "default" not in tiers:
        issues.append("tiers must include 'default'")
    for name, t in tiers.items():
        for k in ("input_per_1k", "output_per_1k"):
            if not isinstance(t.get(k), (int, float)) or t[k] < 0:
                issues.append(f"tiers.{name}.{k} must be a non-negative number")
    caps = p.get("caps", {})
    for cap_name in ("per_call", "per_session", "per_day"):
        c = caps.get(cap_name)
        if c is None:
            issues.append(f"missing caps.{cap_name}")
            continue
        if not isinstance(c.get("usd"), (int, float)) or c["usd"] < 0:
            issues.append(f"caps.{cap_name}.usd must be non-negative number")
        if c.get("on_trip") not in ("degrade", "kill"):
            issues.append(f"caps.{cap_name}.on_trip must be 'degrade' or 'kill'")
        if c.get("on_trip") == "degrade":
            if "degrade_to" not in c:
                issues.append(f"caps.{cap_name}.degrade_to required when on_trip=degrade")
            elif c["degrade_to"] not in tiers:
                issues.append(f"caps.{cap_name}.degrade_to refers to unknown tier {c['degrade_to']!r}")
    if all(caps.get(n, {}).get("usd") is not None for n in ("per_call", "per_session", "per_day")):
        if not (caps["per_day"]["usd"] >= caps["per_session"]["usd"] >= caps["per_call"]["usd"]):
            issues.append("caps must satisfy per_day >= per_session >= per_call")
    ks = p.get("kill_switch_usd_remaining", None)
    if ks is not None and (not isinstance(ks, (int, float)) or ks < 0):
        issues.append("kill_switch_usd_remaining must be null or a non-negative number")
    for line in issues:
        print(f"issue: {line}", file=sys.stderr)
    if issues:
        print(f"{len(issues)} issue(s)", file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

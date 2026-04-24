#!/usr/bin/env python3
"""Lint a rules.json file: duplicate pointers, ambiguous globs, value-class typos.

Usage:
    check_rules.py <rules.json>

Exit codes:
    0 — clean
    1 — at least one issue found
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KNOWN_CLASSES = {
    "int", "float", "bool",
    "string_short", "iso8601", "sha256", "passthrough",
}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    raw = json.loads(Path(argv[1]).read_text())
    issues: list[str] = []
    if raw.get("version") != 1:
        issues.append(f"unsupported version: {raw.get('version')!r}")
    seen: dict[str, dict] = {}
    for r in raw.get("allow", []):
        ptr = r.get("pointer")
        cls = r.get("value_class", "")
        if ptr in seen:
            issues.append(f"duplicate pointer: {ptr!r}")
        seen[ptr] = r
        if cls not in KNOWN_CLASSES and not cls.startswith("string_enum:"):
            issues.append(f"unknown value_class for {ptr!r}: {cls!r}")
        if cls == "passthrough" and ptr in ("", "/"):
            issues.append(f"root passthrough disables redaction: {ptr!r}")
        if cls == "passthrough" and ptr.endswith("/*"):
            issues.append(f"wildcard leaf with passthrough is too permissive: {ptr!r}")
        if not r.get("reason"):
            issues.append(f"missing reason: {ptr!r}")
    for line in issues:
        print(f"issue: {line}", file=sys.stderr)
    if issues:
        print(f"{len(issues)} issue(s)", file=sys.stderr)
        return 1
    print(f"ok: {len(seen)} rule(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Redact a JSON document against an allowlist rule set.

Usage:
    redact.py <rules.json> <input.json> <output.json> [--report <report.jsonl>] [--strict]

Exit codes:
    0 — success, no redactions (or --strict not set)
    2 — success, redactions occurred and --strict was set
    1 — usage / IO / rule-file error

Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ISO8601 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
WS_RUN = re.compile(r"\s{3,}")


def value_class_of(v: Any) -> str:
    """Best-effort observed class for the report."""
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        if SHA256.match(v):
            return "sha256"
        if ISO8601.match(v):
            return "iso8601"
        if len(v) <= 64 and not WS_RUN.search(v):
            return "string_short"
        return "string_long"
    if v is None:
        return "null"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "unknown"


def matches_class(v: Any, cls: str) -> bool:
    if cls == "passthrough":
        return True
    if cls == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if cls == "float":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if cls == "bool":
        return isinstance(v, bool)
    if cls == "string_short":
        return isinstance(v, str) and len(v) <= 64 and not WS_RUN.search(v)
    if cls.startswith("string_enum:"):
        allowed = set(cls[len("string_enum:"):].split("|"))
        return isinstance(v, str) and v in allowed
    if cls == "iso8601":
        return isinstance(v, str) and bool(ISO8601.match(v))
    if cls == "sha256":
        return isinstance(v, str) and bool(SHA256.match(v))
    raise ValueError(f"unknown value_class: {cls}")


def pointer_segments(p: str) -> list[str]:
    if p == "":
        return []
    if not p.startswith("/"):
        raise ValueError(f"pointer must start with /: {p!r}")
    parts = p.split("/")[1:]
    return [seg.replace("~1", "/").replace("~0", "~") for seg in parts]


def pointer_matches(rule_segs: list[str], path_segs: list[str]) -> bool:
    if len(rule_segs) != len(path_segs):
        return False
    for r, p in zip(rule_segs, path_segs):
        if r == "*":
            continue
        if r != p:
            return False
    return True


def lookup_rule(rules: list[dict], path_segs: list[str]) -> dict | None:
    for r in rules:
        if pointer_matches(r["_segs"], path_segs):
            return r
    return None


def render_pointer(segs: list[str]) -> str:
    if not segs:
        return ""
    return "/" + "/".join(s.replace("~", "~0").replace("/", "~1") for s in segs)


def walk(node: Any, path: list[str], rules: list[dict], report: list[dict]) -> Any:
    if isinstance(node, dict):
        return {k: walk(v, path + [k], rules, report) for k, v in node.items()}
    if isinstance(node, list):
        return [walk(v, path + [str(i)], rules, report) for i, v in enumerate(node)]
    # leaf
    rule = lookup_rule(rules, path)
    if rule is None:
        report.append({
            "pointer": render_pointer(path),
            "reason": "not_in_allowlist",
            "observed_class": value_class_of(node),
        })
        return "[REDACTED:not_in_allowlist]"
    if not matches_class(node, rule["value_class"]):
        report.append({
            "pointer": render_pointer(path),
            "reason": "value_class_mismatch",
            "observed_class": value_class_of(node),
            "rule_class": rule["value_class"],
        })
        return "[REDACTED:value_class_mismatch]"
    return node


def load_rules(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    if raw.get("version") != 1:
        raise ValueError(f"unsupported rules version: {raw.get('version')!r}")
    rules = []
    seen_pointers = set()
    for r in raw["allow"]:
        ptr = r["pointer"]
        if ptr in seen_pointers:
            raise ValueError(f"duplicate pointer in rules: {ptr!r}")
        seen_pointers.add(ptr)
        r["_segs"] = pointer_segments(ptr)
        # validate value_class shape
        _ = matches_class(0 if r["value_class"] in ("int","float") else "x", r["value_class"]) \
            if r["value_class"] not in ("passthrough",) else True
        rules.append(r)
    return rules


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    strict = False
    report_path: Path | None = None
    if "--strict" in args:
        strict = True
        args.remove("--strict")
    if "--report" in args:
        i = args.index("--report")
        report_path = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 3:
        print(__doc__, file=sys.stderr)
        return 1
    rules_path, in_path, out_path = (Path(a) for a in args)
    try:
        rules = load_rules(rules_path)
        doc = json.loads(in_path.read_text())
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    report: list[dict] = []
    redacted = walk(doc, [], rules, report)
    out_path.write_text(json.dumps(redacted, indent=2, sort_keys=True) + "\n")
    if report_path is not None:
        report_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in report))
    print(f"redactions: {len(report)}")
    if strict and report:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

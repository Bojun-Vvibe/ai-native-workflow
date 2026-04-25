#!/usr/bin/env python3
"""Detect drift between declared template variables and {{placeholders}} actually used in a prompt body.

Two failure classes that silently break prompt rendering:
  - declared_unused: variable named in the schema/manifest but never referenced
                     in the body (dead config; usually means the body changed
                     but the manifest didn't, or a feature was rolled back
                     and the variable is still being computed at the call site).
  - used_undeclared: {{placeholder}} present in the body with no matching
                     manifest entry (will render as the literal "{{...}}"
                     in production unless the renderer happens to be lenient
                     — most are not, and the result is a leaked template
                     fragment to the model).

Plus a soft warning class:
  - duplicate_declaration: the same variable name declared twice in the
                           manifest (last-wins behavior is renderer-specific
                           and not portable; flag it so the author picks one).

Pure stdlib. Reads a single JSON document with two fields:
  {"manifest": {"vars": [{"name": "...", "type": "..."}, ...]},
   "body": "the prompt text containing {{placeholders}}"}

Output is sorted JSON for cron-friendly diffing.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict, field
from typing import Any

# Conservative placeholder regex: {{ name }} with optional whitespace.
# Names: ASCII letters, digits, underscore, dot (for nested like user.id),
# but must start with a letter or underscore. Anything weirder is not a
# placeholder we recognize — caller should normalize first.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}")


@dataclass(frozen=True)
class Finding:
    kind: str  # "declared_unused" | "used_undeclared" | "duplicate_declaration"
    name: str
    detail: str


@dataclass
class Report:
    ok: bool
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [asdict(f) for f in self.findings],
        }


def detect(doc: dict[str, Any]) -> Report:
    manifest = doc.get("manifest") or {}
    body = doc.get("body")
    if not isinstance(body, str):
        raise ValueError("doc.body must be a string")

    vars_list = manifest.get("vars") or []
    if not isinstance(vars_list, list):
        raise ValueError("doc.manifest.vars must be a list")

    declared_counts: dict[str, int] = {}
    declared_order: list[str] = []
    for entry in vars_list:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError(f"manifest var entry missing 'name': {entry!r}")
        name = entry["name"]
        if not isinstance(name, str) or not name:
            raise ValueError(f"manifest var name must be non-empty string: {entry!r}")
        if name not in declared_counts:
            declared_order.append(name)
        declared_counts[name] = declared_counts.get(name, 0) + 1

    declared = set(declared_counts)
    used_with_pos: list[tuple[str, int]] = []
    for m in PLACEHOLDER_RE.finditer(body):
        used_with_pos.append((m.group(1), m.start()))
    used = {n for n, _ in used_with_pos}

    findings: list[Finding] = []

    # duplicate declarations (warning-class, but reported as findings;
    # caller decides severity)
    for name in declared_order:
        if declared_counts[name] > 1:
            findings.append(Finding(
                kind="duplicate_declaration",
                name=name,
                detail=f"declared {declared_counts[name]} times in manifest.vars",
            ))

    # declared but not used
    for name in declared_order:
        if name not in used:
            findings.append(Finding(
                kind="declared_unused",
                name=name,
                detail="declared in manifest.vars but no matching {{placeholder}} in body",
            ))

    # used but not declared (report first occurrence position so author can find it)
    first_pos: dict[str, int] = {}
    for n, pos in used_with_pos:
        if n not in first_pos:
            first_pos[n] = pos
    for name in sorted(used - declared):
        findings.append(Finding(
            kind="used_undeclared",
            name=name,
            detail=f"{{{{{name}}}}} appears in body at byte offset {first_pos[name]} but not declared in manifest.vars",
        ))

    # deterministic ordering: by (kind, name)
    findings.sort(key=lambda f: (f.kind, f.name))
    return Report(ok=not findings, findings=findings)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <input.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    report = detect(doc)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Detect Go code where an error return is assigned to `_` and silently dropped.

Heuristic, line-based scan over Go source. Flags patterns like:
  _, err := f()        # OK (err is captured)
  _ = f()              # FLAGGED if f returns error
  x, _ := f()          # FLAGGED — error explicitly discarded
  result, _ = f()      # FLAGGED
  _, _ = f()           # FLAGGED

We can't fully resolve types from text, so we flag any assignment to `_`
on the right-hand side of a call where `_` appears in a multi-return
unpacking position. This is the canonical "swallowed error" pattern in
Go review comments and is a frequent LLM hallucination when generating
example code.

Usage:
  python3 detector.py <file.go> [<file.go> ...]
Exit code: number of findings (capped at 255).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Match LHS like: a, _ := / _ , b = / _, _ := / _ = call(...)
# Captures the LHS tuple before := or =.
ASSIGN_RE = re.compile(
    r"^\s*([A-Za-z_][\w]*\s*(?:,\s*[A-Za-z_][\w]*\s*)*)"  # LHS identifiers (and underscores)
    r"(?::?=)\s*"                                          # := or =
    r"(.+)$"                                               # RHS
)

CALL_RE = re.compile(r"[A-Za-z_][\w\.]*\s*\(")


def lhs_has_blank(lhs: str) -> bool:
    parts = [p.strip() for p in lhs.split(",")]
    return "_" in parts


def rhs_is_call(rhs: str) -> bool:
    rhs = rhs.strip()
    # Strip trailing comments
    if "//" in rhs:
        rhs = rhs.split("//", 1)[0].strip()
    return bool(CALL_RE.search(rhs))


def scan(path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    in_block_comment = False
    for i, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw
        # Strip block comments crudely
        if in_block_comment:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block_comment = False
            else:
                continue
        if "/*" in line:
            before, _, rest = line.partition("/*")
            if "*/" in rest:
                line = before + rest.split("*/", 1)[1]
            else:
                line = before
                in_block_comment = True
        # Skip line comments
        if "//" in line:
            line = line.split("//", 1)[0]
        m = ASSIGN_RE.match(line)
        if not m:
            continue
        lhs, rhs = m.group(1), m.group(2)
        if not lhs_has_blank(lhs):
            continue
        if not rhs_is_call(rhs):
            continue
        # Single LHS `_` only flagged if RHS looks like it could return error.
        # We use a name heuristic: function names that commonly return error.
        parts = [p.strip() for p in lhs.split(",")]
        if parts == ["_"]:
            # Flag conservatively when call name suggests fallible op.
            if not re.search(
                r"\b("
                r"Close|Open|Read|Write|Flush|Sync|Marshal|Unmarshal|Decode|Encode|"
                r"Parse|Exec|Query|Scan|Get|Post|Do|Dial|Listen|Accept|Connect|"
                r"Remove|Rename|Mkdir|Stat|Chmod|Chown|Copy|Set|Send|Recv|"
                r"Lookup|Compile|Validate|Start|Stop|Run|Wait"
                r")\b",
                rhs,
            ):
                continue
        findings.append((i, raw.rstrip()))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file.go> [<file.go> ...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"{arg}: not found", file=sys.stderr)
            continue
        for line_no, text in scan(p):
            print(f"{p}:{line_no}: ignored error: {text.strip()}")
            total += 1
    print(f"findings: {total}")
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

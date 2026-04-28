#!/usr/bin/env python3
"""Detect Java code that builds a String via `+=` (or `s = s + ...`) inside a loop.

This is the canonical "use StringBuilder" anti-pattern: each `+=` on a
String allocates a new char[] and copies the old contents, turning a
linear concatenation into O(n^2). LLMs frequently emit this when asked
to "join these strings" or "build a CSV row" because the `+=` form is
shorter and reads naturally.

Heuristic, line-based scan over Java source:

  1. Track loop nesting. We enter a loop scope when we see a line that
     begins with `for (`, `while (`, or `do {` (with optional whitespace
     and modifiers). We track brace depth from that point and pop the
     scope when depth returns to where the loop opened.
  2. Inside any loop scope, flag a line if it matches:
       <ident> += "..."           (string literal RHS)
       <ident> += <ident>         (any RHS) AND <ident> was declared as String
       <ident> = <ident> + ...    same-name self-assign concat
     when the LHS identifier was previously declared as `String <ident>`
     in the current file (best-effort scan-back).
  3. We also flag any `+=` on an identifier whose declaration line in
     the file is `String <ident>` regardless of RHS type, because Java
     `String += int` still goes through the slow path.

We intentionally do NOT flag StringBuilder/StringBuffer .append() calls
inside loops -- those are the fix.

Usage:
  python3 detector.py <file.java> [<file.java> ...]
Exit code: number of findings (capped at 255).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LOOP_HEAD_RE = re.compile(r"^\s*(?:\}\s*)?(for|while|do)\s*[({]")
STRING_DECL_RE = re.compile(
    r"\b(?:final\s+|static\s+|private\s+|public\s+|protected\s+)*"
    r"String\s+([A-Za-z_]\w*)\s*(?:=|;)"
)
PLUSEQ_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\+=\s*(.+?);\s*(?://.*)?$")
SELF_CONCAT_RE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*=\s*\1\s*\+\s*(.+?);\s*(?://.*)?$"
)


def strip_line_comment(s: str) -> str:
    # naive: drop // ... not inside a string
    out = []
    in_str = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i - 1] != "\\"):
            in_str = not in_str
            out.append(c)
        elif not in_str and c == "/" and i + 1 < len(s) and s[i + 1] == "/":
            break
        else:
            out.append(c)
        i += 1
    return "".join(out)


def collect_string_vars(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for ln in lines:
        clean = strip_line_comment(ln)
        for m in STRING_DECL_RE.finditer(clean):
            names.add(m.group(1))
    return names


def scan(path: Path) -> list[tuple[int, str, str]]:
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    string_vars = collect_string_vars(raw_lines)
    findings: list[tuple[int, str, str]] = []

    # Loop scope tracking using brace counting.
    # Each entry: (open_brace_depth, kind)
    loop_stack: list[tuple[int, str]] = []
    depth = 0
    pending_loop_kind: str | None = None  # set when we see `for (` but `{` not yet on same line

    for i, raw in enumerate(raw_lines, 1):
        line = strip_line_comment(raw)

        # Detect loop header
        loop_m = LOOP_HEAD_RE.match(line)
        if loop_m:
            pending_loop_kind = loop_m.group(1)

        # If we're inside a loop, evaluate the line for findings BEFORE
        # adjusting depth (so a `}` line that closes the loop isn't itself
        # checked as inside).
        if loop_stack:
            stripped = line.strip()
            m_pe = PLUSEQ_RE.match(stripped)
            m_sc = SELF_CONCAT_RE.match(stripped)
            cand: tuple[str, str] | None = None
            if m_pe:
                lhs, rhs = m_pe.group(1), m_pe.group(2).strip()
                if lhs in string_vars or rhs.startswith('"'):
                    cand = (lhs, f'+= {rhs}')
            elif m_sc:
                lhs, rhs = m_sc.group(1), m_sc.group(2).strip()
                if lhs in string_vars or rhs.startswith('"') or '"' in rhs:
                    cand = (lhs, f'= {lhs} + {rhs}')
            if cand:
                findings.append((i, cand[0], raw.rstrip()))

        # Update brace depth based on this line.
        opens = line.count("{")
        closes = line.count("}")
        # Push loop scope when its `{` appears.
        if pending_loop_kind and opens > 0:
            # The opening brace for the loop body is on this line.
            loop_stack.append((depth, pending_loop_kind))
            pending_loop_kind = None
        depth += opens - closes
        # Pop any loop scopes whose body has now closed.
        while loop_stack and depth <= loop_stack[-1][0]:
            loop_stack.pop()

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file.java> [<file.java> ...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"{arg}: not found", file=sys.stderr)
            continue
        for line_no, var, text in scan(p):
            print(f"{p}:{line_no}: string concat in loop ({var}): {text.strip()}")
            total += 1
    print(f"findings: {total}")
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

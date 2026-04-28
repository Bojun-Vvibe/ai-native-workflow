#!/usr/bin/env python3
"""Detect unquoted shell variable expansions in bash/sh scripts.

Unquoted `$var` / `${var}` / `$(cmd)` is the #1 cause of "works on my
machine, breaks in CI" failures: a path with a space becomes two args,
a glob char triggers pathname expansion, and an empty value silently
disappears. LLMs frequently emit unquoted expansions because they read
more cleanly and most tutorial snippets do the same.

This detector flags expansions of `$var` / `${var}` / `$(cmd)` /
`` `cmd` `` that are NOT inside double or single quotes, in contexts
where word-splitting matters: command arguments, test conditions,
assignments to arrays, and redirection targets.

Whitelist (intentionally NOT flagged):
  * Right-hand side of a simple `var=$other` assignment -- bash treats
    this as if quoted (no word-splitting, no globbing).
  * Inside `[[ ... ]]` -- bash also disables word-splitting there.
  * Inside arithmetic `(( ... ))` or `$(( ... ))`.
  * Numeric-only contexts like `$?`, `$#`, `$$`, `$!` are skipped
    (no splitting concern).
  * Inside a heredoc body (best-effort tracker).
  * Lines whose first non-whitespace is `#` (comments).

Usage:
  python3 detector.py <file.sh> [<file.sh> ...]
Exit code: number of findings (capped at 255).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Match a $expansion that we'd want to consider.
# Variants: $name, ${...}, $(...), `...`
EXPANSION_RE = re.compile(
    r"""
    \$\{[^}]+\}            # ${var} or ${var:-default}
  | \$\([^)]*\)            # $(cmd)
  | \$[A-Za-z_][A-Za-z0-9_]*   # $name
  | `[^`]*`                # `cmd`
    """,
    re.VERBOSE,
)

ASSIGN_RHS_RE = re.compile(r"^\s*[A-Za-z_]\w*=(\S*)\s*(?:#.*)?$")
HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")


def char_in_quote_state(line: str) -> list[str]:
    """For each char index in `line`, return one of:
       'd' inside double-quoted string
       's' inside single-quoted string
       'D' inside $((...)) or ((...)) arithmetic
       'B' inside [[ ... ]] test
       '.' otherwise (default)
    Best-effort: doesn't handle every nesting edge case but handles
    the common ones.
    """
    state = ['.'] * len(line)
    i = 0
    in_d = False
    in_s = False
    bracket_depth = 0  # for [[ ]]
    paren_arith = 0    # for (( )) or $(( ))
    while i < len(line):
        c = line[i]
        nxt = line[i + 1] if i + 1 < len(line) else ''
        if in_s:
            state[i] = 's'
            if c == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            state[i] = 'd'
            if c == '\\' and nxt:
                state[i + 1] = 'd'
                i += 2
                continue
            if c == '"':
                in_d = False
            i += 1
            continue
        # Not in any string
        if c == "'":
            in_s = True
            state[i] = 's'
            i += 1
            continue
        if c == '"':
            in_d = True
            state[i] = 'd'
            i += 1
            continue
        # [[ ... ]]
        if c == '[' and nxt == '[':
            bracket_depth += 1
            state[i] = 'B'
            state[i + 1] = 'B'
            i += 2
            continue
        if c == ']' and nxt == ']' and bracket_depth > 0:
            state[i] = 'B'
            state[i + 1] = 'B'
            bracket_depth -= 1
            i += 2
            continue
        # $(( ... )) or (( ... ))
        if c == '$' and nxt == '(' and line[i + 2:i + 3] == '(':
            paren_arith += 1
            state[i] = 'D'
            state[i + 1] = 'D'
            state[i + 2] = 'D'
            i += 3
            continue
        if c == '(' and nxt == '(' and paren_arith == 0 and bracket_depth == 0:
            paren_arith += 1
            state[i] = 'D'
            state[i + 1] = 'D'
            i += 2
            continue
        if c == ')' and nxt == ')' and paren_arith > 0:
            state[i] = 'D'
            state[i + 1] = 'D'
            paren_arith -= 1
            i += 2
            continue
        if bracket_depth > 0:
            state[i] = 'B'
        elif paren_arith > 0:
            state[i] = 'D'
        i += 1
    return state


def scan(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    in_heredoc: str | None = None  # terminator string while inside heredoc

    for i, raw in enumerate(lines, 1):
        # Heredoc body skip
        if in_heredoc is not None:
            if raw.strip() == in_heredoc:
                in_heredoc = None
            continue
        h = HEREDOC_START_RE.search(raw)
        if h:
            in_heredoc = h.group(2)
            # Continue scanning the start line itself, then heredoc body
            # is skipped on subsequent lines.

        stripped = raw.lstrip()
        if not stripped or stripped.startswith('#'):
            continue

        # Whitelist: simple `VAR=$other` assignment (RHS is one expansion).
        m_a = ASSIGN_RHS_RE.match(raw)
        if m_a and EXPANSION_RE.fullmatch(m_a.group(1) or ""):
            continue

        states = char_in_quote_state(raw)
        # Trim a trailing line-comment: a `#` that is not inside any
        # string and is preceded by whitespace (or starts the line) ends
        # the shell command. We walk the state vector to find it.
        comment_cut = len(raw)
        for idx, ch in enumerate(raw):
            if ch != '#':
                continue
            if states[idx] in ('d', 's'):
                continue
            # Must be at start or preceded by whitespace to be a comment.
            if idx == 0 or raw[idx - 1].isspace():
                comment_cut = idx
                break
        scan_line = raw[:comment_cut]
        for m in EXPANSION_RE.finditer(scan_line):
            start = m.start()
            tok = m.group(0)
            # Skip $? $# $$ $! $0..$9 -- these are integers / pids /
            # exit codes, no splitting concern in practice.
            if re.fullmatch(r"\$[?#$!0-9]", tok):
                continue
            st = states[start]
            if st in ('d', 's', 'B', 'D'):
                continue  # safe: inside quotes or [[ ]] or arithmetic
            findings.append((i, tok, raw.rstrip()))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file.sh> [<file.sh> ...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"{arg}: not found", file=sys.stderr)
            continue
        for line_no, tok, text in scan(p):
            print(f"{p}:{line_no}: unquoted expansion {tok}: {text.strip()}")
            total += 1
    print(f"findings: {total}")
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

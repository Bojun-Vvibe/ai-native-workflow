#!/usr/bin/env python3
"""Detect Elixir `Code.eval_string` / `Code.eval_quoted` / `Code.eval_file`
calls (and the `Code.compile_string` family).

These functions take a binary, parse it as Elixir source, and execute
it inside the current BEAM node with the caller's permissions. They are
the Elixir equivalent of `eval()` on a string. If any portion of the
input is derived from user input, network traffic, or DB content, this
is a textbook remote code execution vector.

LLM-emitted Elixir reaches for `Code.eval_string` especially often when:

* The model wants to "interpret a config string" and forgets that
  Elixir has proper config / parsers (`Config`, `Jason`, `Toml`).
* The model translates a Python `eval(s)` literally instead of using
  pattern matching or a proper DSL.
* The model "dynamically calls a function" via
  `Code.eval_string("MyMod." <> name <> "()")` instead of `apply/3`.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Functions in the `Code` module that take a string and execute / compile it.
# `Code.string_to_quoted` is intentionally NOT included — it parses but does
# not execute, so it's not the same hazard.
DANGEROUS_FUNS = (
    "eval_string",
    "eval_quoted",
    "eval_file",
    "compile_string",
    "compile_quoted",
    "require_file",
    "compile_file",
)


def strip_comments_and_strings(line: str) -> str:
    """Blank out string contents and trailing `#` comments while preserving
    column positions. Handles:

    * `# ...` line comments (but not `?#` charlist literal of `#`).
    * `"..."` and `'...'` string / charlist literals with `\\` escapes.
    * `\"\"\"` heredocs are NOT tracked here (handled at the file level by
      a separate flag in `scan_file`).
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "?" and i + 1 < n:
                # `?#` etc. — char literal, copy through 2 chars.
                out.append(ch)
                out.append(line[i + 1])
                i += 2
                continue
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch == '"' or ch == "'":
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == in_s:
            out.append(ch)
            in_s = None
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


# Match `Code.<fun>(` where <fun> is one of the dangerous funs. We also
# match the pipe form `... |> Code.<fun>(`. We do NOT match a bare
# `eval_string(` without the `Code.` prefix (which would be ambiguous
# with user-defined functions).
RE_CODE_CALL = re.compile(
    r"\bCode\s*\.\s*(" + "|".join(DANGEROUS_FUNS) + r")\b"
)

# Heredoc start/end: `\"\"\"` on its own (possibly with leading whitespace
# and trailing chars). Elixir also has `'''` heredocs.
RE_HEREDOC_DQ = re.compile(r'"""')
RE_HEREDOC_SQ = re.compile(r"'''")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    in_heredoc: str | None = None  # None | '"""' | "'''"

    for idx, raw_line in enumerate(raw.splitlines()):
        lineno = idx + 1

        if in_heredoc is not None:
            # Look for the matching terminator on this line.
            term_re = RE_HEREDOC_DQ if in_heredoc == '"""' else RE_HEREDOC_SQ
            if term_re.search(raw_line):
                in_heredoc = None
            continue

        # Detect heredoc opening. If a heredoc opens AND closes on the
        # same line (rare), we just treat the line as plain.
        dq_count = len(RE_HEREDOC_DQ.findall(raw_line))
        sq_count = len(RE_HEREDOC_SQ.findall(raw_line))
        opens_heredoc: str | None = None
        if dq_count % 2 == 1:
            opens_heredoc = '"""'
        elif sq_count % 2 == 1:
            opens_heredoc = "'''"

        scrub = strip_comments_and_strings(raw_line)
        for m in RE_CODE_CALL.finditer(scrub):
            fun = m.group(1)
            findings.append(
                (
                    path,
                    lineno,
                    m.start() + 1,
                    f"code-{fun.replace('_', '-')}",
                    raw_line.strip(),
                )
            )

        if opens_heredoc is not None:
            in_heredoc = opens_heredoc

    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            files = list(p.rglob("*.ex")) + list(p.rglob("*.exs"))
            for sub in sorted(files):
                yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

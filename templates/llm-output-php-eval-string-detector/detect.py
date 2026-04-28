#!/usr/bin/env python3
"""Detect PHP `eval(...)` call sites outside comments/strings.

`eval($code)` in PHP executes an arbitrary string as PHP source. It is
one of the classic remote-code-execution vectors: any taint reaching
the argument turns the whole process into an interpreter for the
attacker. LLM-generated PHP frequently reaches for `eval()` to
"dynamically build a function" or "run user-supplied formulas"
because that is the most direct mapping from the prompt — but in
production code the right answer is almost always a parser, a
whitelist dispatch, or `call_user_func`.

Also flagged (same family of dynamic-code execution):
- `assert($string)` — pre-PHP 8 evaluates the string as code.
- `create_function(...)` — deprecated, eval-backed.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


DANGEROUS = (
    "eval",
    "create_function",
    "assert",
)
RE_CALL = re.compile(r"\b(" + "|".join(DANGEROUS) + r")\s*\(")


def strip_comments_and_strings(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Blank out PHP `//` and `#` line comments, `/* */` block comments,
    and `'...'` / `"..."` string literals while preserving columns.
    Returns (scrubbed_line, still_in_block_comment).

    Note: PHP heredoc/nowdoc are multi-line and rare in LLM output for
    this anti-pattern; we do not attempt to model them and accept the
    occasional false positive on heredoc bodies.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_squote = False
    in_dquote = False
    block = in_block_comment
    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""
        if block:
            if ch == "*" and nxt == "/":
                out.append("  ")
                i += 2
                block = False
                continue
            out.append(" ")
            i += 1
            continue
        if in_squote:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                out.append(ch)
                in_squote = False
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if in_dquote:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                out.append(ch)
                in_dquote = False
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # Not in any string or block comment.
        if ch == "/" and nxt == "/":
            out.append(" " * (n - i))
            break
        if ch == "#":
            out.append(" " * (n - i))
            break
        if ch == "/" and nxt == "*":
            out.append("  ")
            i += 2
            block = True
            continue
        if ch == "'":
            out.append(ch)
            in_squote = True
            i += 1
            continue
        if ch == '"':
            out.append(ch)
            in_dquote = True
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), block


def is_method_call(scrubbed: str, start: int) -> bool:
    """Avoid flagging `$x->eval(` or `Class::eval(` — those are user
    methods that happen to share the name, not the language builtin."""
    j = start - 1
    while j >= 0 and scrubbed[j] == " ":
        j -= 1
    if j < 0:
        return False
    if scrubbed[j] == ">" and j >= 1 and scrubbed[j - 1] == "-":
        return True
    if scrubbed[j] == ":" and j >= 1 and scrubbed[j - 1] == ":":
        return True
    return False


def is_function_definition(scrubbed: str, start: int) -> bool:
    """Skip `function eval(...)` user definitions."""
    prefix = scrubbed[:start].rstrip()
    return prefix.endswith("function")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    raw_lines = raw.splitlines()
    in_block = False
    for idx, raw_line in enumerate(raw_lines):
        lineno = idx + 1
        scrub, in_block = strip_comments_and_strings(raw_line, in_block)
        for m in RE_CALL.finditer(scrub):
            name = m.group(1)
            start = m.start()
            if is_method_call(scrub, start):
                continue
            if is_function_definition(scrub, start):
                continue
            findings.append(
                (path, lineno, start + 1, f"php-{name}-call", raw_line.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(
                list(p.rglob("*.php"))
                + list(p.rglob("*.phtml"))
                + list(p.rglob("*.inc"))
            ):
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

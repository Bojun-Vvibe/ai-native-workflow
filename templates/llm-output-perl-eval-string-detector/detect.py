#!/usr/bin/env python3
"""Detect Perl `eval EXPR` (string-eval) calls.

Perl has two `eval` forms:

* `eval { BLOCK }` — compile-time, used for try/catch. SAFE.
* `eval EXPR`     — runtime string compile + execute. Equivalent to
                    `exec()` on a string. UNSAFE except in extremely
                    narrow build-time uses.

LLM-emitted Perl frequently produces the string form, often with
interpolated variables, which is a textbook code-injection vector.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments_and_strings(line: str) -> str:
    """Blank out '...' / "..." string contents and trailing '#' comments,
    preserving column positions. Skips '#' that sit inside `$#`, `@#`,
    `%#` (perl sigil tricks) or right after `$`/`@`/`%` (variable names
    starting with #), and skips `#` inside an already-open string.
    Crude but enough for line-based linting."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = None  # None | "'" | '"'
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "#":
                prev = line[i - 1] if i > 0 else ""
                if prev in ("$", "@", "%"):
                    out.append(ch)
                    i += 1
                    continue
                # rest of line is a comment
                out.append(" " * (n - i))
                break
            if ch == "'" or ch == '"':
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string literal
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


# Match a bareword `eval` not preceded by a sigil/word char and not
# followed by `{` (which would be the safe block form). What follows
# can be a quoted string, a `qq(...)`, a variable, or a function call.
RE_EVAL = re.compile(r"(?<![\w$@%>])eval\b\s*([^\s{])")


def is_block_eval(after_char: str) -> bool:
    return after_char == "{"


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    raw_lines = raw.splitlines()
    in_pod = False
    in_heredoc = False
    heredoc_terminator = ""

    for idx, raw_line in enumerate(raw_lines):
        lineno = idx + 1
        stripped = raw_line.strip()

        # POD documentation blocks: =pod ... =cut
        if not in_pod and stripped.startswith("=") and not stripped.startswith("=cut"):
            in_pod = True
            continue
        if in_pod:
            if stripped.startswith("=cut"):
                in_pod = False
            continue

        # Very simple heredoc tracking: <<EOF / <<"EOF" / <<'EOF'.
        if in_heredoc:
            if raw_line.rstrip() == heredoc_terminator:
                in_heredoc = False
            continue
        m_hd = re.search(r"<<\s*[~]?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", raw_line)
        # Heredoc starts on the NEXT line; only register if `<<NAME` looks
        # like a real heredoc (i.e. the line ends within the same statement).
        # We also still scan the current line.

        scrub = strip_comments_and_strings(raw_line)

        for m in RE_EVAL.finditer(scrub):
            after = m.group(1)
            if is_block_eval(after):
                continue
            # Some Perl uses `eval(...)` where `...` starts with `{` after
            # the paren — that's still string eval.
            findings.append(
                (path, lineno, m.start() + 1, "eval-string", raw_line.strip())
            )

        if m_hd:
            # Register heredoc only if there's a `<<` immediately followed
            # by an identifier; conservative.
            heredoc_terminator = m_hd.group(1)
            in_heredoc = True

    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(list(p.rglob("*.pl")) + list(p.rglob("*.pm")) + list(p.rglob("*.t"))):
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

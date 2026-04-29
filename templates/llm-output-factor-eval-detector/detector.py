#!/usr/bin/env python3
"""Detect runtime-string code-execution sinks in Factor source.

See README.md for rationale and rules. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"!\s*factor-eval-ok\b")

# Sinks (matched against a line that has comments and string contents
# blanked).
RE_EVAL_PUBLIC = re.compile(r"\beval\(\s")
RE_EVAL_PRIVATE = re.compile(r"\(eval\)")
RE_PARSE_FRESH = re.compile(r"\bparse-fresh\b[^\n]*\bcall\b")
RE_PARSE_STRING = re.compile(r"\bparse-string\b[^\n]*\bcall\b")
RE_RUN_FILE = re.compile(r"\brun-file\b")

# A "word reference" preceding the sink, used to detect dynamic
# argument origin. Any non-space, non-quote, non-paren token.
RE_WORD = re.compile(r"[A-Za-z0-9>:.\-+*/?$%&=<@_]+")


def _blank(s: str, start: int, end: int) -> str:
    return s[:start] + (" " * (end - start)) + s[end:]


def strip_comments_and_strings(line: str) -> str:
    """Blank Factor comments and the *contents* of string literals.

    Comments:
      * `! ...`     to end of line
      * `#! ...`    to end of line (shebang-style)
      * `( ... )`   stack-effect comment, single-line only

    String literals: `"..."` with `\\"` escape. Only the contents are
    blanked; the surrounding quotes survive so the lexical structure
    of the line is preserved for downstream regexes.
    """
    n = len(line)
    out = list(line)
    i = 0
    in_str = False
    while i < n:
        ch = out[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                out[i] = " "
                out[i + 1] = " "
                i += 2
                continue
            if ch == '"':
                in_str = False
                i += 1
                continue
            out[i] = " "
            i += 1
            continue
        # Not in string.
        if ch == '"':
            in_str = True
            i += 1
            continue
        # `#!` shebang-style comment.
        if ch == "#" and i + 1 < n and out[i + 1] == "!":
            for j in range(i, n):
                out[j] = " "
            break
        # `!` line comment -- but only when it stands as its own token
        # (preceded by start-of-line or whitespace) so we do not eat
        # `!` inside a word like `set!`.
        if ch == "!" and (i == 0 or out[i - 1] == " " or out[i - 1] == "\t"):
            # Require trailing space or EOL so `!=`-style does not trip.
            if i + 1 == n or out[i + 1] in (" ", "\t"):
                for j in range(i, n):
                    out[j] = " "
                break
        # `( ` stack-effect comment opener (must be its own token).
        if ch == "(" and (i == 0 or out[i - 1] in (" ", "\t")) \
                and i + 1 < n and out[i + 1] in (" ", "\t"):
            close = -1
            for j in range(i + 2, n):
                if out[j] == ")" and (j + 1 == n or out[j + 1] in (" ", "\t")):
                    close = j
                    break
            if close != -1:
                for j in range(i, close + 1):
                    out[j] = " "
                i = close + 1
                continue
        i += 1
    return "".join(out)


def is_dynamic_before(scrub: str, sink_start: int) -> bool:
    """True if the scrubbed text *before* the sink contains a word
    reference outside any quoted region. We approximate "outside any
    quoted region" by scanning the prefix and tracking quote parity."""
    prefix = scrub[:sink_start]
    # Walk the prefix, skipping over surviving "..." spans (their
    # contents are already blanks but the quotes are still there).
    in_str = False
    cleaned = []
    for ch in prefix:
        if ch == '"':
            in_str = not in_str
            cleaned.append(" ")
            continue
        cleaned.append(" " if in_str else ch)
    cleaned_s = "".join(cleaned)
    # Strip the most recent literal `"..."` close so the very last
    # token before the sink, if it is a closing quote, is not counted.
    # Then look for any word token.
    for m in RE_WORD.finditer(cleaned_s):
        tok = m.group(0)
        # Bare numbers do not qualify as a "code reference".
        if tok.replace(".", "", 1).replace("-", "", 1).isdigit():
            continue
        return True
    return False


def is_factor_file(path: Path) -> bool:
    return path.suffix == ".factor"


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)

        for pat, base in (
            (RE_EVAL_PUBLIC, "factor-eval"),
            (RE_EVAL_PRIVATE, "factor-eval-private"),
            (RE_PARSE_FRESH, "factor-parse-fresh-call"),
            (RE_PARSE_STRING, "factor-parse-string-call"),
            (RE_RUN_FILE, "factor-run-file"),
        ):
            for m in pat.finditer(scrub):
                kind = base
                if is_dynamic_before(scrub, m.start()):
                    kind = f"{base}-dynamic"
                findings.append(
                    (path, idx, m.start() + 1, kind, raw.strip())
                )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_factor_file(sub):
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

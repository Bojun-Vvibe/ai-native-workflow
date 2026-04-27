#!/usr/bin/env python3
"""Detect malformed angle-bracket link destinations in markdown.

CommonMark allows two forms of inline link destination:

    [text](https://example.com)         # bare
    [text](<https://example.com>)       # angle-bracketed (allows spaces)

The angle-bracketed form requires a balanced `<` and `>`. LLM output
sometimes emits a half-open form:

    [text](<https://example.com)        # opening `<`, no closing `>`
    [text](https://example.com>)        # closing `>`, no opening `<`
    [text](<https://exa mple.com)       # `<` plus a space but no closing

These render as literal text in most renderers and break the link silently.

This detector scans for inline link patterns `](...)` and flags destinations
where:

  * the destination starts with `<` but does not end with `>`, or
  * the destination ends with `>` but does not start with `<`, or
  * the destination contains a `<` or `>` in the middle that is not part of
    a balanced wrap.

Fenced code blocks (``` and ~~~) and inline code spans are skipped.

Usage:
    python3 detector.py path/to/file.md [...]

Exit code: 0 if all clean, 1 if any file has findings.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Match `](destination)` greedily up to the first unescaped `)`.
# We capture the destination so we can inspect it.
LINK_RE = re.compile(r"\]\(([^)\n]*)\)")
FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")


def classify(dest: str) -> str | None:
    """Return a problem description, or None if the destination is fine."""
    d = dest.strip()
    if not d:
        return None
    starts = d.startswith("<")
    ends = d.endswith(">")
    if starts and ends:
        inner = d[1:-1]
        if "<" in inner or ">" in inner:
            return "nested or extra angle bracket inside <...>"
        return None
    if starts and not ends:
        return "opening '<' without closing '>'"
    if ends and not starts:
        return "closing '>' without opening '<'"
    # Neither — bare URL form. Stray brackets here are still suspicious.
    if "<" in d or ">" in d:
        return "stray '<' or '>' in bare destination"
    return None


def scan(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{path}: cannot read ({e})", file=sys.stderr)
        return findings
    in_fence = False
    fence_marker = ""
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m:
            tok = m.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = tok[0]
            elif tok[0] == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        # Strip inline code so we don't flag bracketed destinations inside it.
        stripped = re.sub(r"`+[^`\n]*`+", "", line)
        for lm in LINK_RE.finditer(stripped):
            dest = lm.group(1)
            problem = classify(dest)
            if problem:
                findings.append((lineno, dest, problem))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py FILE [FILE ...]", file=sys.stderr)
        return 2
    bad_files = 0
    for arg in argv[1:]:
        p = Path(arg)
        results = scan(p)
        if results:
            bad_files += 1
            for lineno, dest, problem in results:
                print(f"{p}:{lineno}: {problem}: ({dest})")
    return 1 if bad_files else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

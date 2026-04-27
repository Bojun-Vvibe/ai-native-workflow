#!/usr/bin/env python3
"""Detect invalid markdown backslash escapes.

Per CommonMark, a backslash escape (`\\X`) is only meaningful when `X` is one of
the ASCII punctuation characters. Any other use (e.g. `\\z`, `\\a`, `\\1`,
`\\ `) leaves the backslash as a literal character, which is almost never what
the author intended. LLM output frequently emits things like `\\n` (expecting a
newline), `\\t`, or `\\d` (regex habit) inside prose, producing visibly wrong
rendering.

This detector flags every occurrence of `\\X` in non-code-fence regions where
`X` is NOT ASCII punctuation. Inside fenced code blocks (``` or ~~~) the line
is skipped because escapes do not apply there.

Usage:
    python3 detector.py path/to/file.md [...]

Exit code is the number of files that had at least one finding (capped at 1
for clean clarity in shell pipelines: 0 = clean, >0 = issues).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# CommonMark "ASCII punctuation" set that may follow a backslash.
ASCII_PUNCT = set(r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~""")

# Find a backslash followed by any non-whitespace, non-newline character.
# We accept `\\` (escaped backslash) as valid since `\` is in the punct set.
ESCAPE_RE = re.compile(r"\\(.)")

FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")


def scan(path: Path) -> list[tuple[int, int, str]]:
    findings: list[tuple[int, int, str]] = []
    in_fence = False
    fence_marker = ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{path}: cannot read ({e})", file=sys.stderr)
        return findings

    for lineno, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m:
            tok = m.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = tok[0]  # ` or ~
            elif tok[0] == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        # Skip inline code spans: anything between matched backticks
        # Simple stripping: remove `...` runs before checking escapes.
        stripped = re.sub(r"`+[^`\n]*`+", "", line)
        for em in ESCAPE_RE.finditer(stripped):
            ch = em.group(1)
            if ch == "\n":
                continue
            if ch not in ASCII_PUNCT:
                col = em.start() + 1
                findings.append((lineno, col, f"\\{ch}"))
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
            for lineno, col, tok in results:
                print(f"{p}:{lineno}:{col}: invalid escape {tok!r}")
    return 1 if bad_files else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

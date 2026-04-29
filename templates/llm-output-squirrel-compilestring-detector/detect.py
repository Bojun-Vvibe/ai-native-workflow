#!/usr/bin/env python3
"""Detect Squirrel `compilestring(...)` runtime code-evaluation
sinks.

Squirrel is a small embeddable scripting language used in games
(notably Left 4 Dead 2's vscripts) and embedded systems. Its
standard library exposes:

    compilestring(src [, bindname])

which compiles a Squirrel source string at runtime and returns a
closure that, when called, executes that code in the host VM with
full access to the root table. A compiled-then-called closure is
the canonical eval-equivalent in Squirrel.

Whenever the source argument is anything other than an audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable: a config file, a network
response, a chat command, an entity keyvalue. Because the produced
closure runs with the full host environment, this is equivalent to
a Lua `loadstring(...)()`.

LLM-emitted Squirrel code reaches for `compilestring` whenever the
model wants a "tiny scripting hook" or "user-supplied formula" and
does not know the safer patterns (a small interpreter over a fixed
grammar, a data-only config table, or sandboxing via a fresh root
table with `setroottable`).

What this flags
---------------
* `compilestring(...)`    — primary sink
* `::compilestring(...)`  — explicitly root-scoped variant

We anchor on optional `::`, the symbol, and an opening `(`.
Identifiers that merely contain `compilestring` (`my_compilestring`,
`compilestringify`) do not match.

Suppression
-----------
Append `// eval-ok` (or `# eval-ok`) to the line to silence a
vetted call.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.nut`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"(?://|#)\s*eval-ok\b")

# Match optional ::, then `compilestring` not preceded by an
# identifier character (so `my_compilestring` does not match), then
# `(`. We rely on the masking pass to strip strings/comments.
RE_COMPILESTRING = re.compile(
    r"(?<![A-Za-z0-9_])(::\s*)?compilestring\s*\("
)


def mask_squirrel_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    Squirrel lexical rules we cover:
      * `//` line comments
      * `#`  line comments (Squirrel accepts `#` as a line comment)
      * `/* ... */` block comments (no nesting)
      * `"..."` strings with `\\` escapes
      * `'...'` character literals with `\\` escapes
      * `@"..."` verbatim strings (a `""` inside is an escaped quote)
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # // line comment
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        # # line comment
        if ch == "#":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        # /* block comment */
        if ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                j = n
            else:
                j += 2
            for k in range(i, j):
                if text[k] != "\n":
                    out[k] = " "
            i = j
            continue
        # @"..." verbatim string
        if ch == "@" and nxt == '"':
            k = i + 2
            while k < n:
                if text[k] == '"':
                    if k + 1 < n and text[k + 1] == '"':
                        k += 2
                        continue
                    break
                k += 1
            end = k + 1 if k < n else n
            for m in range(i + 2, max(i + 2, end - 1)):
                if text[m] != "\n":
                    out[m] = " "
            i = end
            continue
        # "..." regular string
        if ch == '"':
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == '"' or c == "\n":
                    break
                k += 1
            end = k + 1 if k < n and text[k] == '"' else k
            for m in range(i + 1, max(i + 1, end - 1)):
                if text[m] != "\n":
                    out[m] = " "
            i = end
            continue
        # '...' character / short string literal
        if ch == "'":
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == "'" or c == "\n":
                    break
                k += 1
            end = k + 1 if k < n and text[k] == "'" else k
            for m in range(i + 1, max(i + 1, end - 1)):
                if text[m] != "\n":
                    out[m] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    masked = mask_squirrel_comments_and_strings(text)
    raw_lines = text.splitlines()
    masked_lines = masked.splitlines()
    n = min(len(raw_lines), len(masked_lines))
    for idx in range(n):
        raw = raw_lines[idx]
        scrub = masked_lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_COMPILESTRING.finditer(scrub):
            kind = (
                "squirrel-root-compilestring"
                if m.group(1)
                else "squirrel-compilestring"
            )
            findings.append(
                (path, idx + 1, m.start() + 1, kind, raw.strip())
            )
    return findings


def is_squirrel_file(path: Path) -> bool:
    return path.suffix == ".nut"


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_squirrel_file(sub):
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

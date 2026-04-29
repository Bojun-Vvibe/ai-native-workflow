#!/usr/bin/env python3
"""Detect dynamic-evaluation sinks in Io programs.

The Io language exposes several methods that take a *string* and
evaluate it as Io source at runtime. The headline ones are:

* `doString(src)`            -- evaluate `src` in the receiver's context
* `doFile(path)`             -- read `path` and evaluate its contents
* `doMessage(msg)`            -- evaluate a pre-parsed message tree
* `Lobby doString(src)`       -- same, scoped at the Lobby
* `Object compileString(src)` -- compile `src` into an executable block

When the argument to any of these is a *literal* string with no
concatenation, that's a smell but rarely a security bug -- the LLM
usually just meant to write the code inline. When the argument is
built from variables, message sends, or `..` concatenation, this is
the Io equivalent of `eval(user_input)`.

Io has no `--` line comment; comments are `//`, `#`, or `/* ... */`.
Strings are `"..."` (double-quoted) or `\"\"\"...\"\"\"` (triple).
Single quotes are not strings in Io.

What this flags
---------------
On a per-line basis, after blanking comments and string contents:

| Pattern                                  | Kind                       |
| ---------------------------------------- | -------------------------- |
| `<recv> doString(<arg>)` arg dynamic     | `io-dostring-dynamic`      |
| `<recv> doString(<arg>)` arg literal     | `io-dostring`              |
| `<recv> doFile(<arg>)` arg dynamic       | `io-dofile-dynamic`        |
| `<recv> doFile(<arg>)` arg literal       | `io-dofile`                |
| `<recv> doMessage(<arg>)`                | `io-domessage`             |
| `<recv> compileString(<arg>)` dynamic    | `io-compilestring-dynamic` |
| `<recv> compileString(<arg>)` literal    | `io-compilestring`         |

A "literal" argument is one that, after string-content scrubbing,
contains only a `"  "` placeholder pair with nothing else (no `..`,
no identifiers, no parens).

Out of scope
------------
* We do not try to prove a variable is sanitized.
* `Object perform(name, args...)` (reflective method dispatch) is
  not flagged here -- that's a separate smell.
* We do not handle the rare `\"\"\"triple\"\"\"` Io string form
  specially; its contents are still blanked correctly because the
  scanner treats each `"` as a toggle.

Suppression: append `// io-eval-ok` on the line.

Usage
-----
    python3 detector.py <file_or_dir> [<file_or_dir> ...]

Recurses into directories looking for `*.io` files. Exit code 1 if
any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"//\s*io-eval-ok\b|#\s*io-eval-ok\b")

# We capture: METHOD ( ARG )  where ARG has no nested parens.
# Receiver (if any) is whatever precedes; we don't need to capture it.
RE_DOSTRING = re.compile(r"\bdoString\s*\(([^()]*)\)")
RE_DOFILE = re.compile(r"\bdoFile\s*\(([^()]*)\)")
RE_DOMESSAGE = re.compile(r"\bdoMessage\s*\(([^()]*)\)")
RE_COMPILESTRING = re.compile(r"\bcompileString\s*\(([^()]*)\)")


def strip_comments_and_strings(line: str) -> str:
    """Blank `"..."` string contents, `//` and `#` line comments, and
    `/* ... */` block-comment fragments on this line. Backslash
    escapes inside strings are honored."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_dq = False
    in_block = False
    while i < n:
        ch = line[i]
        if in_block:
            if ch == "*" and i + 1 < n and line[i + 1] == "/":
                out.append("  ")
                i += 2
                in_block = False
                continue
            out.append(" ")
            i += 1
            continue
        if not in_dq:
            # block-comment start
            if ch == "/" and i + 1 < n and line[i + 1] == "*":
                out.append("  ")
                i += 2
                in_block = True
                continue
            # line-comment start
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                out.append(" " * (n - i))
                break
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_dq = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside double-quoted string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_bare_string_literal(scrubbed_arg: str) -> bool:
    """A bare `"..."` literal scrubs to a `" ... "` pair containing
    only spaces. Reject anything with extra tokens (concatenation,
    identifiers, message sends)."""
    s = scrubbed_arg.strip()
    if len(s) < 2:
        return False
    if s[0] != '"' or s[-1] != '"':
        return False
    inner = s[1:-1]
    return inner.strip() == ""


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
        for m in RE_DOSTRING.finditer(scrub):
            arg = m.group(1)
            kind = "io-dostring" if is_bare_string_literal(arg) else "io-dostring-dynamic"
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        for m in RE_DOFILE.finditer(scrub):
            arg = m.group(1)
            kind = "io-dofile" if is_bare_string_literal(arg) else "io-dofile-dynamic"
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        for m in RE_DOMESSAGE.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "io-domessage", raw.strip())
            )
        for m in RE_COMPILESTRING.finditer(scrub):
            arg = m.group(1)
            kind = (
                "io-compilestring"
                if is_bare_string_literal(arg)
                else "io-compilestring-dynamic"
            )
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*.io")):
                if sub.is_file():
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

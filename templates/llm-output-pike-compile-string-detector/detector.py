#!/usr/bin/env python3
"""Detect dynamic-evaluation sinks in Pike programs.

Pike (https://pike.lysator.liu.se/) is a C-like, dynamically-typed
language with a runtime compiler exposed to user code. The headline
eval-shaped APIs are:

* `compile_string(src)`
* `compile_string(src, filename)`
* `compile_string(src, filename, handler)`
* `compile_file(path)`
* `compile(src)`                       -- low-level compile of a CPP-expanded blob
* `cpp(src)`                            -- run the C-pre-processor on a string
                                           (sink because the result is usually
                                           handed straight to `compile`)
* `Function `predef::compile_string`    -- explicit module-prefixed form

Once any of these returns a program, the typical next step is
`<program>()` to instantiate it, at which point the attacker-supplied
source executes. LLM-generated Pike code reaches for `compile_string`
the way python code reaches for `eval` -- to "just run that string".

What this flags
---------------
On a per-line basis, after blanking comments and string contents:

| Pattern                                  | Kind                          |
| ---------------------------------------- | ----------------------------- |
| `compile_string(<arg>)` arg dynamic      | `pike-compile-string-dynamic` |
| `compile_string(<arg>)` arg literal      | `pike-compile-string`         |
| `compile_file(<arg>)` arg dynamic        | `pike-compile-file-dynamic`   |
| `compile_file(<arg>)` arg literal        | `pike-compile-file`           |
| `compile(<arg>)`                         | `pike-compile`                |
| `cpp(<arg>)` arg dynamic                 | `pike-cpp-dynamic`            |

The `predef::` and `Function::` module prefixes are tolerated by
allowing optional `[A-Za-z_:]+` before the bareword.

A "literal" argument means that, after string-content scrubbing,
the argument span contains only an empty pair of `"..."` quotes
(no concatenation, no identifiers, no `+`, no parens).

Out of scope
------------
* `Function f = compile_string("...")(); f();` -- we flag the
  compile_string call, not the subsequent invocation.
* `master()->compile_string(...)` is matched (we don't require a
  bare call).
* We don't try to prove the variable is sanitized.

Suppression: append `// pike-eval-ok` on the line.

Usage
-----
    python3 detector.py <file_or_dir> [<file_or_dir> ...]

Recurses into directories looking for `*.pike`, `*.pmod`, `*.pmod.in`,
and `*.pike.in`. Exit code 1 if any findings, 0 otherwise. python3
stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"//\s*pike-eval-ok\b")

# Allow an optional `predef::` / `Function::` / `master()->` style prefix
# (but stop short of trying to parse Pike) by matching just the bareword
# call. The tokens `compile_string` / `compile_file` / `compile` / `cpp`
# are unique enough as bare identifiers.
RE_COMPILE_STRING = re.compile(r"\bcompile_string\s*\(([^()]*)\)")
RE_COMPILE_FILE = re.compile(r"\bcompile_file\s*\(([^()]*)\)")
# `compile(` -- but not `compile_` (already matched above) and not as
# part of an identifier suffix.
RE_COMPILE = re.compile(r"(?<![A-Za-z0-9_])compile\s*\(([^()]*)\)")
RE_CPP = re.compile(r"(?<![A-Za-z0-9_])cpp\s*\(([^()]*)\)")


def strip_comments_and_strings(line: str) -> str:
    """Blank `"..."` string contents, `//` line comments, and
    `/* ... */` block-comment fragments on this line. Pike strings
    are double-quoted; backslash escapes are honored. Pike also has
    `#"..."` pre-quoted strings, which we treat as ordinary strings
    here (the leading `#` is left in place; the `"..."` body is
    blanked the same way)."""
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
            if ch == "/" and i + 1 < n and line[i + 1] == "*":
                out.append("  ")
                i += 2
                in_block = True
                continue
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
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
    s = scrubbed_arg.strip()
    if len(s) < 2:
        return False
    if s[0] != '"' or s[-1] != '"':
        return False
    return s[1:-1].strip() == ""


def is_first_arg_literal(scrubbed_arg: str) -> bool:
    """compile_string takes (src, filename?, handler?). We want to
    classify by the *first* arg only -- the filename is allowed to
    be a variable. Split on the first top-level comma in the scrubbed
    span (since strings have been blanked, commas inside them are
    gone)."""
    head = scrubbed_arg.split(",", 1)[0]
    return is_bare_string_literal(head)


PIKE_EXTS = (".pike", ".pmod", ".pmod.in", ".pike.in")


def is_pike_file(path: Path) -> bool:
    name = path.name
    return any(name.endswith(ext) for ext in PIKE_EXTS)


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
        for m in RE_COMPILE_STRING.finditer(scrub):
            arg = m.group(1)
            kind = (
                "pike-compile-string"
                if is_first_arg_literal(arg)
                else "pike-compile-string-dynamic"
            )
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        for m in RE_COMPILE_FILE.finditer(scrub):
            arg = m.group(1)
            kind = (
                "pike-compile-file"
                if is_bare_string_literal(arg)
                else "pike-compile-file-dynamic"
            )
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        for m in RE_COMPILE.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "pike-compile", raw.strip())
            )
        for m in RE_CPP.finditer(scrub):
            arg = m.group(1)
            if is_bare_string_literal(arg):
                # cpp("literal") is a documentation-style smell; skip.
                continue
            findings.append(
                (path, idx, m.start() + 1, "pike-cpp-dynamic", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_pike_file(sub):
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

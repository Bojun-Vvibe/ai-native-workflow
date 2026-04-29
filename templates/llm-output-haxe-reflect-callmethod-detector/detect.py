#!/usr/bin/env python3
"""Detect Haxe `Reflect.callMethod` / `Reflect.field`-into-call /
`Type.createInstance` runtime dynamic-dispatch sinks.

Haxe is a statically typed language, but its `Reflect` and `Type`
modules expose escape hatches that defeat the type checker and turn
strings into method calls or class instantiations:

    Reflect.callMethod(obj, Reflect.field(obj, name), args)
    Reflect.callMethod(obj, method, args)
    Reflect.field(obj, name)        // followed by a call
    Reflect.setField(obj, name, v)
    Type.createInstance(cls, args)
    Type.createEmptyInstance(cls)
    Type.resolveClass(name)         // followed by createInstance

Whenever `name`/`method`/`cls` is anything other than a manifest,
audited literal, the program is dispatching to a method or class
chosen at runtime from data that may be attacker-controllable
(config, RPC frame, query string, deserialized JSON).

LLM-generated Haxe code reaches for `Reflect.callMethod` and
`Type.createInstance` whenever the model wants "a tiny RPC layer"
or "let the caller pick which handler to run" without knowing the
safer patterns (a closed `Map<String, Method>` dispatch table, or
a sealed enum + switch).

What this flags
---------------
* `Reflect.callMethod(...)`         - primary dynamic-call sink
* `Reflect.field(obj, x)`           - flagged on its own (typically a
                                       precursor to a call, and even
                                       reads can leak fields)
* `Reflect.setField(obj, x, v)`     - mirror write sink
* `Type.createInstance(cls, args)`  - dynamic constructor
* `Type.createEmptyInstance(cls)`   - bypasses constructor entirely
* `Type.resolveClass(...)`          - string-to-Class lookup, the
                                       front half of a dynamic ctor

Suppression
-----------
Append `// reflect-ok` to the line to silence a vetted call.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.hx`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"//\s*reflect-ok\b")

# Haxe identifiers may include $ but not . — so `Reflect.callMethod`
# is a single qualified token. We require `(` after the name to be
# sure it's a call.
RE_REFLECT_CALL = re.compile(
    r"\bReflect\.(callMethod|field|setField)\s*\("
)
RE_TYPE_CALL = re.compile(
    r"\bType\.(createInstance|createEmptyInstance|resolveClass)\s*\("
)


def mask_haxe_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    Haxe lexical rules we cover:
      * `// line` comments (to end of line)
      * `/* block */` comments (non-nesting; Haxe's standard form)
      * `"..."` and `'...'` strings with `\\` escapes
        (single-quoted strings additionally support `${expr}` string
        interpolation; we do NOT unmask the interpolated expression
        because doing so would risk false positives — a literal
        `'${Reflect.callMethod(o,m,a)}'` is itself a dynamic call,
        but it's exceedingly rare and we prefer the simpler model:
        anything inside a string is masked.)
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # // line comment
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        # /* block */ comment
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                j = n
            else:
                j += 2
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        # "..." / '...' string with \ escapes
        if ch == '"' or ch == "'":
            quote = ch
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == quote:
                    break
                if c == "\n":
                    # unterminated string on this line: treat as ending
                    # at newline for safety
                    break
                k += 1
            end = k + 1 if k < n and text[k] == quote else k
            for m in range(i + 1, max(i + 1, end - 1)):
                out[m] = text[m] if text[m] == "\n" else " "
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
    masked = mask_haxe_comments_and_strings(text)
    raw_lines = text.splitlines()
    masked_lines = masked.splitlines()
    n = min(len(raw_lines), len(masked_lines))
    for idx in range(n):
        raw = raw_lines[idx]
        scrub = masked_lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_REFLECT_CALL.finditer(scrub):
            kind = "haxe-reflect-" + m.group(1).lower()
            findings.append(
                (path, idx + 1, m.start() + 1, kind, raw.strip())
            )
        for m in RE_TYPE_CALL.finditer(scrub):
            kind = "haxe-type-" + m.group(1).lower()
            findings.append(
                (path, idx + 1, m.start() + 1, kind, raw.strip())
            )
    return findings


def is_haxe_file(path: Path) -> bool:
    return path.suffix == ".hx"


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_haxe_file(sub):
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

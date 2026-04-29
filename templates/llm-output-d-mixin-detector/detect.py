#!/usr/bin/env python3
"""Detect D-language `mixin(...)` string-evaluation sites.

The D programming language has a `mixin` expression / declaration that
takes a compile-time string and *compiles it as D source* in place:

    mixin("int x = 1 + 2;");
    auto v = mixin(buildExpr(name));

This is structurally identical to `eval` over D source. Whenever the
argument is anything other than a manifest string literal pasted by
the author, you have either:

* a code-injection sink (the argument depends on file/network input
  resolved at compile time via `import("...")` or CTFE'd I/O), or
* an obscure metaprogramming trick that should be a `template` /
  `static foreach` / proper AST construction instead.

LLM-emitted D code reaches for `mixin` whenever it doesn't know the
right metaprogramming primitive. Almost every such use should be
flagged for a human to confirm.

What this flags
---------------
* `mixin(expr)`              — expression-statement form
* `mixin (expr)` / multiline — whitespace tolerated
* `mixin template Foo() { ...; mixin("..."); ... }` — inner mixin
* `mixin!"..."` template-instantiation shorthand (e.g. with
  `bitfields!`) — flagged because the argument is still a code
  string evaluated at compile time

Bare `mixin Foo!();` (template *mixin*, not string mixin) is NOT
flagged: the argument is a template identifier, not a string.

Suppression
-----------
Append `// mixin-ok` to the line to silence a known-safe usage.

Out of scope (deliberately)
---------------------------
* `__traits(compiles, ...)` — meta-introspection, not eval.
* `import("file")` on its own — file read; only dangerous when its
  result feeds a `mixin`.
* Run-time DSL evaluators built on top of mixin — covered downstream.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.d` and `*.di`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"//\s*mixin-ok\b")

# `mixin(` at command/expression position. We require either start of
# line, whitespace, or one of `;{}(=,!?:&|+*/<>` immediately before
# `mixin`. Followed by optional whitespace and `(`.
RE_MIXIN_CALL = re.compile(
    r"(?:^|(?<=[\s;{}()=,!?:&|+\-*/<>]))"
    r"mixin\s*\("
)

# `mixin!"..."` or `mixin!\"...\"` — template-shorthand form where the
# argument is a string literal coding more D source.
RE_MIXIN_BANG_STR = re.compile(
    r"(?:^|(?<=[\s;{}()=,!?:&|+\-*/<>]))"
    r"mixin\s*!\s*[\"`]"
)


def mask_d_comments_and_strings(text: str) -> str:
    """Return text with comments and string-literal *contents* replaced
    by spaces while preserving column positions.

    Handles:
      * `// line` comments
      * `/* block */` comments (non-nesting)
      * `/+ nest /+ inner +/ outer +/` nesting block comments
      * `"..."`  with `\\` escapes
      * `` `...` ``  WYSIWYG strings (no escapes)
      * `r"..."`  WYSIWYG with `r` prefix
      * `q"(...)"`, `q"[...]"`, `q"{...}"`, `q"<...>"` token strings
        (delimiter-paired). For these we mask conservatively: blank
        from the opening `q"` through the matching close.

    The masker keeps the masking *outside* of strings so that
    `mixin("evil")` text stays visible, but the literal `"evil"`
    contents become spaces. That's exactly what we need: we only care
    about the surrounding `mixin(` call, not the string contents.
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
                out[k] = " " if text[k] != "\n" else "\n"
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
                out[k] = text[k] if text[k] == "\n" else " "
            i = j
            continue
        # /+ nesting block +/
        if ch == "/" and nxt == "+":
            depth = 1
            k = i + 2
            while k < n and depth > 0:
                if text[k] == "/" and k + 1 < n and text[k + 1] == "+":
                    depth += 1
                    k += 2
                    continue
                if text[k] == "+" and k + 1 < n and text[k + 1] == "/":
                    depth -= 1
                    k += 2
                    continue
                k += 1
            for m in range(i, k):
                out[m] = text[m] if text[m] == "\n" else " "
            i = k
            continue
        # WYSIWYG `...`
        if ch == "`":
            j = text.find("`", i + 1)
            if j == -1:
                j = n
            else:
                j += 1
            # keep the opening/closing backtick visible, blank inside
            for k in range(i + 1, max(i + 1, j - 1)):
                out[k] = text[k] if text[k] == "\n" else " "
            i = j
            continue
        # r"..." raw
        if ch == "r" and nxt == '"':
            j = text.find('"', i + 2)
            if j == -1:
                j = n
            else:
                j += 1
            for k in range(i + 2, max(i + 2, j - 1)):
                out[k] = text[k] if text[k] == "\n" else " "
            i = j
            continue
        # q"(...)" token strings
        if ch == "q" and nxt == '"' and i + 2 < n:
            opener = text[i + 2]
            closer = {"(": ")", "[": "]", "{": "}", "<": ">"}.get(opener)
            if closer is not None:
                # find the matching `closer"` sequence
                k = i + 3
                depth = 1
                while k < n and depth > 0:
                    if text[k] == opener:
                        depth += 1
                    elif text[k] == closer:
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                # k now points to closing `closer`; expect `"` after.
                end = k + 2 if k < n else n
                for m in range(i + 3, max(i + 3, end - 1)):
                    out[m] = text[m] if text[m] == "\n" else " "
                i = end
                continue
        # "..." with \\ escapes
        if ch == '"':
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == '"':
                    break
                k += 1
            end = k + 1 if k < n else n
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
    masked = mask_d_comments_and_strings(text)
    raw_lines = text.splitlines()
    masked_lines = masked.splitlines()
    # splitlines() may give different counts if the file ends without
    # a newline and a string spans EOF; align defensively.
    n = min(len(raw_lines), len(masked_lines))
    for idx in range(n):
        raw = raw_lines[idx]
        scrub = masked_lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_MIXIN_CALL.finditer(scrub):
            findings.append(
                (path, idx + 1, m.start() + 1, "d-mixin-call", raw.strip())
            )
        for m in RE_MIXIN_BANG_STR.finditer(scrub):
            findings.append(
                (path, idx + 1, m.start() + 1, "d-mixin-bang-string", raw.strip())
            )
    return findings


def is_d_file(path: Path) -> bool:
    return path.suffix in (".d", ".di")


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_d_file(sub):
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

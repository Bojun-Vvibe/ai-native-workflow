#!/usr/bin/env python3
"""Detect Scheme `(eval ...)` of string-derived forms.

Scheme has a small but well-known anti-idiom for "build code as a
string and run it":

    (eval (read (open-input-string s))
          (interaction-environment))

This is the Scheme equivalent of Python's `exec(s)` or shell
`eval $cmd`. It silently bypasses the macro hygiene the language is
famous for, defeats `raco check-syntax` / Geiser-style static
analysis, breaks separate compilation, and — when any fragment of
the string flows from user input, an S-expression file written by
some other tool, an HTTP body, or a database column — turns into
arbitrary-code execution in the host Scheme runtime (with full FFI
reach in many implementations).

LLM-emitted Scheme code reaches for this pattern to dynamically
construct definitions, build expressions in a loop, or "let the user
type a snippet and run it". In every such case there is a safer,
more idiomatic alternative:

* dynamic "variable name"    -> a hash-table keyed by symbol/string
* dynamic expression         -> a `define-syntax` / `syntax-rules`
                                macro (compile-time, hygienic)
* parsing untrusted data     -> read into a *form* and pattern-match
                                it as data; never `eval` it

What this flags
---------------
A call of the form `(eval (read ...) ...)` where the inner `(read
...)` is reading from a string port — or any direct
`(eval (read-string ...))` / `(eval (string->expr ...))` style
spelling commonly used in R6RS/R7RS, Racket, Guile, Chicken, etc.

Specifically we flag:

* `(eval (read (open-input-string ...)) ...)`
* `(eval (read (open-string-input-port ...)) ...)`     ; R6RS spelling
* `(eval (with-input-from-string ... read) ...)`
* `(eval (read-from-string ...))`                       ; SRFI-30-ish
* `(eval (string->expression ...))`
* `(eval (call-with-input-string ... read) ...)`

Out of scope (deliberately)
---------------------------
* `(eval form env)` where `form` is a quoted/quasiquoted s-expression
  literal — that's normal metaprogramming, not string-eval.
* `(read port)` *not* immediately consumed by `eval` — the result is
  a datum (data), harmless on its own.
* `(load "file.scm")` — that loads from a file path; covered by a
  separate concern.

Suppression
-----------
Trailing `; eval-string-ok` comment on the same line suppresses that
finding — use sparingly, e.g. for a unit-test helper that rounds-trips
an internal sexpr.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.scm, *.ss, *.sld, *.sps,
*.rkt (Racket).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Common shapes of "eval a form that came from a string". The `(?s)`
# lets `.` match newlines so multi-line spellings still match.
RE_EVAL_READ_STRING_PORT = re.compile(
    r"(?s)\(\s*eval\s*\(\s*read\s*\(\s*"
    r"(?:open-input-string|open-string-input-port|call-with-input-string)\b"
)
RE_EVAL_WITH_INPUT_FROM_STRING = re.compile(
    r"(?s)\(\s*eval\s*\(\s*with-input-from-string\b"
)
RE_EVAL_READ_FROM_STRING = re.compile(
    r"(?s)\(\s*eval\s*\(\s*(?:read-from-string|string->expression|string->expr)\b"
)

RE_SUPPRESS = re.compile(r";\s*eval-string-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out "..." string contents and `; ...` line comments,
    and `#| ... |#` would need block-comment handling but we treat
    each line independently and only handle line comments here.

    Scheme uses `;` for line comments, `"..."` for strings with
    `\\` escapes, `#\\x` / `#\\space` for character literals, and
    `#| ... |#` for block comments. We do NOT mask `#| |#` block
    comments — they're rare in real code and a multi-line scrubber
    would over-engineer this scanner. The extremely rare false
    positive can be silenced with `; eval-string-ok`."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    while i < n:
        ch = line[i]
        if not in_s:
            # character literal: #\x — skip the next two chars so
            # `#\;` and `#\"` don't trigger comment/string state.
            if ch == "#" and i + 1 < n and line[i + 1] == "\\" and i + 2 < n:
                out.append(line[i:i + 3])
                i += 3
                continue
            if ch == ";":
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_s = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_s = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def scan_text(text: str) -> list[tuple[int, int, str, str]]:
    """Return [(line, col, kind, snippet), ...]."""
    raw_lines = text.splitlines()
    suppressed = {i + 1 for i, l in enumerate(raw_lines) if RE_SUPPRESS.search(l)}
    scrubbed_lines = [strip_comments_and_strings(l) for l in raw_lines]
    flat = "\n".join(scrubbed_lines)

    line_starts = [0]
    for l in scrubbed_lines:
        line_starts.append(line_starts[-1] + len(l) + 1)

    def offset_to_linecol(off: int) -> tuple[int, int]:
        for ln, start in enumerate(line_starts):
            if start > off:
                return ln, off - line_starts[ln - 1] + 1
        return len(line_starts), off - line_starts[-1] + 1

    findings: list[tuple[int, int, str, str]] = []
    for kind, regex in (
        ("eval-read-string-port", RE_EVAL_READ_STRING_PORT),
        ("eval-with-input-from-string", RE_EVAL_WITH_INPUT_FROM_STRING),
        ("eval-read-from-string", RE_EVAL_READ_FROM_STRING),
    ):
        for m in regex.finditer(flat):
            line, col = offset_to_linecol(m.start())
            if line in suppressed:
                continue
            snippet = raw_lines[line - 1].strip() if 1 <= line <= len(raw_lines) else ""
            findings.append((line, col, kind, snippet))
    findings.sort()
    return findings


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    out: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line, col, kind, snippet in scan_text(text):
        out.append((path, line, col, kind, snippet))
    return out


def iter_targets(roots: list[str]):
    suffixes = {".scm", ".ss", ".sld", ".sps", ".rkt"}
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in suffixes:
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

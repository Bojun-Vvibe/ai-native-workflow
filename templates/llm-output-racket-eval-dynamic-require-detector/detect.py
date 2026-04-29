#!/usr/bin/env python3
"""Detect Racket dynamic-code-loading anti-idioms.

Racket inherits Scheme's `eval` and adds its own dynamic-loading
surface — `dynamic-require`, `dynamic-require-for-syntax`, and the
namespace-reflection routines `eval-syntax`, `namespace-require`,
`load`, and `load/use-compiled`. Each is a legitimate building
block, but each turns into arbitrary-code execution the moment the
*identifier of what to load* (a module path, a syntax object, or a
form) flows from outside the program.

Common LLM-emitted Racket footguns:

    ; 1. Eval a form parsed from a string at runtime.
    (eval (read (open-input-string s))
          (make-base-namespace))

    ; 2. Load a module by string path constructed from input.
    (dynamic-require (string->path user-supplied) 'main)

    ; 3. Eval a syntax object reconstructed from a datum.
    (eval-syntax (datum->syntax #f form) (current-namespace))

    ; 4. The legacy `load` family — runs a whole file in the current
    ;    namespace, with full filesystem access on the path argument.
    (load file-path)
    (load/use-compiled file-path)

    ; 5. namespace-require with a runtime-built module spec.
    (namespace-require `(file ,user-path))

What this flags
---------------
* `(eval (read (open-input-string ...)) ...)`           — string-EVAL
* `(eval (read (open-string-input-port ...)) ...)`      — R6RS-spelling
* `(eval (with-input-from-string ... read) ...)`
* `(eval (call-with-input-string ... read) ...)`
* `(eval (read-from-string ...) ...)`
* `(eval-syntax ...)`                                    — reflective eval
* `(dynamic-require <expr> ...)` where `<expr>` does NOT start with
  a plain `'` quote — i.e. flagged when the spec is computed,
  string-built, or quasiquoted with unquote holes
* `(dynamic-require-for-syntax ...)` (always)
* `(namespace-require ...)` where the spec does NOT start with `'`
* `(load ...)` and `(load/use-compiled ...)` (always — file-EVAL)

Out of scope (deliberately)
---------------------------
* `(dynamic-require 'racket/base 'foo)` — quoted symbol literal,
  resolved at compile time, no string flow. Not flagged.
* `(eval form (make-base-namespace))` where `form` is a quoted
  s-expression literal — normal metaprogramming. Not flagged.
* Macro definitions (`define-syntax`, `syntax-parse`) — those run at
  compile time inside Racket's hygienic macro system.

Suppression
-----------
Trailing `; eval-string-ok` comment on the same line suppresses that
finding — use sparingly, e.g. for a unit-test helper that builds
a known-safe internal sexpr or a sandboxed plug-in loader behind a
`make-evaluator` boundary.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.rkt, *.rktl, *.rktd, *.scrbl.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# string-EVAL family (same shapes as the scheme-eval detector,
# repeated here for self-containment).
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
# Reflective syntax-EVAL.
RE_EVAL_SYNTAX = re.compile(r"(?s)\(\s*eval-syntax\b")

# load / load-with-compiled — always file-EVAL. Use a negative
# lookahead on `[A-Za-z0-9_/-]` AFTER the form name to avoid matching
# `(load-plugin ...)`, `(loadable? ...)`, etc. The `/` in
# `load/use-compiled` is part of the canonical name; we list each
# variant explicitly and require the next char to be whitespace, `)`,
# or end-of-string.
RE_LOAD = re.compile(
    r"(?s)\(\s*(?:load|load/use-compiled|load-relative|load-extension)(?=[\s\)])"
)

# dynamic-require / -for-syntax / namespace-require — flag when the
# first argument is NOT a quoted literal (i.e., not `'sym`, not
# `\`(sym ...)`, not a literal string `"..."`). We approximate this
# by capturing the next non-whitespace token and rejecting it only
# when it starts with `'` (quote), `\`` (quasiquote inside Racket),
# or `"` (string literal — which IS a path string, but at least it
# can be reviewed in-source).
RE_DYNAMIC_REQUIRE_HEAD = re.compile(
    r"(?s)\(\s*(dynamic-require(?:-for-syntax)?|namespace-require)\s+(\S)"
)


RE_SUPPRESS = re.compile(r";\s*eval-string-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Mask `; ...` line comments and `"..."` string contents on a
    single line. Racket also has `#| ... |#` block comments and
    `#;` datum comments — we deliberately do not handle these
    (rare in real code; suppression comment is the safety valve).
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    while i < n:
        ch = line[i]
        if not in_s:
            # `#\x` character literal — don't let `#\;` open a comment.
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
        ("eval-syntax", RE_EVAL_SYNTAX),
        ("load-file", RE_LOAD),
    ):
        for m in regex.finditer(flat):
            line, col = offset_to_linecol(m.start())
            if line in suppressed:
                continue
            snippet = raw_lines[line - 1].strip() if 1 <= line <= len(raw_lines) else ""
            findings.append((line, col, kind, snippet))

    # dynamic-require / namespace-require: flag only when the first
    # arg is NOT a plain quoted literal. We treat `'sym` as safe
    # (compile-time constant). Quasiquote `` ` `` is treated as
    # *unsafe* because it commonly carries unquote (`,`) holes that
    # interpolate runtime values into the module spec — the very
    # thing we want to surface. A user with a known-pure quasiquote
    # can suppress on the line.
    for m in RE_DYNAMIC_REQUIRE_HEAD.finditer(flat):
        head = m.group(1)
        first_ch = m.group(2)
        if first_ch == "'":
            continue
        line, col = offset_to_linecol(m.start())
        if line in suppressed:
            continue
        snippet = raw_lines[line - 1].strip() if 1 <= line <= len(raw_lines) else ""
        kind = "dynamic-require-computed" if head.startswith("dynamic-require") \
            else "namespace-require-computed"
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
    suffixes = {".rkt", ".rktl", ".rktd", ".scrbl"}
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

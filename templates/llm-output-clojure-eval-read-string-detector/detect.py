#!/usr/bin/env python3
"""Detect Clojure `(eval (read-string ...))` (string-eval) calls.

Clojure has a well-known anti-idiom for "build code as a string and
run it":

    (eval (read-string (str "(def model-" i " (fit data))")))

This is the Clojure equivalent of Python's `exec(s)` or shell
`eval $cmd`. It silently bypasses the compiler's macro hygiene,
defeats `clj-kondo` / `eastwood` static analysis, breaks AOT
compilation guarantees, and — when any fragment of the string flows
from user input, an EDN file, an HTTP body, or a database column —
turns into arbitrary-code execution in the Clojure runtime (which
has full JVM reach: `System/exit`, `Runtime/exec`, reflection,
arbitrary class loading).

LLM-emitted Clojure code reaches for this pattern to dynamically
construct var names, build forms, or "loop and create N defs". In
every such case there is a safer, more idiomatic alternative:

* dynamic var name           -> use a `def`-by-`intern` with a symbol,
                                or (better) a map keyed by keyword/string
* dynamic form construction  -> use the syntax-quote reader (`` ` ``)
                                with `~` / `~@` unquote, or `quasiquote`
                                via `clojure.template`
* metaprogramming            -> write a macro (compile-time, hygienic),
                                not runtime `eval`
* parsing untrusted EDN data -> `clojure.edn/read-string` (data only,
                                no code)

What this flags
---------------
A call of the form `(eval (read-string ...))` or
`(load-string ...)` — both of which take a string and execute it as
Clojure code. We also flag the fully-qualified spellings:

* `(eval (read-string s))`
* `(eval (clojure.core/read-string s))`
* `(clojure.core/eval (read-string s))`
* `(load-string s)`
* `(clojure.core/load-string s)`

Out of scope (deliberately)
---------------------------
* `(clojure.edn/read-string s)` — that reads EDN *data*, not code,
  and is the recommended way to parse untrusted input. NOT flagged
  even when wrapped in `eval` is impossible (edn/read-string returns
  data, not a form).
* `(eval form)` where `form` is a quoted/unquoted s-expression
  literal — that's normal metaprogramming, not string-eval.
* `(read-string s)` *not* immediately wrapped in `eval` — the result
  is a Clojure form (data), which on its own is harmless. The
  dangerous step is the `eval`.

Suppression
-----------
Trailing `;; eval-read-string-ok` comment on the same line suppresses
that finding — use sparingly, e.g. for a REPL-helper macro whose
input is fully internal.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.clj, *.cljs, *.cljc, *.edn
(edn is scanned only for `load-string`/`eval` literal forms — rare
but possible in eval-on-load configs).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# (eval (read-string ...)) and friends. The `(?s)` lets `.` match
# newlines so we catch multi-line spellings. Whitespace between the
# tokens is permissive.
RE_EVAL_READ_STRING = re.compile(
    r"(?s)\(\s*(?:clojure\.core/)?eval\s*\(\s*(?:clojure\.core/)?read-string\b"
)
RE_LOAD_STRING = re.compile(
    r"(?s)\(\s*(?:clojure\.core/)?load-string\b"
)

RE_SUPPRESS = re.compile(r";;\s*eval-read-string-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out "..." string contents and trailing `;` comments,
    preserving column positions.

    Clojure uses `;` (single semicolon and up) for line comments and
    `"..."` for strings with `\\` escapes. Character literals like
    `\\;` and `\\"` are single-token (no string state). We do not try
    to handle `#"..."` regex literals specially; their contents are
    masked the same as a normal string."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    while i < n:
        ch = line[i]
        if not in_s:
            # character literal: \x, \space, \newline — skip the next
            # token char so a `\;` or `\"` doesn't trigger comment/string.
            if ch == "\\" and i + 1 < n:
                out.append(ch)
                out.append(line[i + 1])
                i += 2
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
        ("eval-read-string", RE_EVAL_READ_STRING),
        ("load-string", RE_LOAD_STRING),
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
    suffixes = {".clj", ".cljs", ".cljc", ".edn"}
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

#!/usr/bin/env python3
"""Detect R `eval(parse(text=...))` (string-eval) calls.

R has a well-known anti-idiom for "build code as a string and run it":

    eval(parse(text = paste0("model_", i, " <- lm(...)")))

This is the R equivalent of Python's `exec(s)` or shell `eval $cmd`.
It silently bypasses lexical scoping, defeats syntax checking,
breaks `R CMD check` static analysis, and — when any fragment of the
string flows from user input, a CSV cell, an HTTP parameter, or a
database column — turns into arbitrary-code execution.

LLM-emitted R code reaches for this pattern to dynamically construct
variable names, build formulas, or "loop and create N models". In
every such case there is a safer, more idiomatic alternative:

* dynamic variable name      -> use a list / named vector / env
* dynamic formula            -> use `as.formula(paste0(...))` then `lm(formula, data)`
* dynamic column reference   -> use `[[name]]` or `dplyr::sym(name)`
* metaprogramming            -> use `bquote()` / `substitute()` / `rlang::expr()`

What this flags
---------------
A call of the form `eval(parse(...))` where the `parse(...)` call
contains a `text =` (or `text=`) argument, or a positional first
argument that is clearly a string expression rather than a file path.

Specifically we flag:

* `eval(parse(text = x))`
* `eval(parse(text=paste0(...)))`
* `eval(parse(text = sprintf(...)))`
* `evalq(parse(text = x))`              — same anti-idiom
* `base::eval(parse(text = x))`         — fully qualified

Out of scope (deliberately)
---------------------------
* `parse(file = "script.R")` followed by `eval(...)` — that's a
  legitimate "source another file" pattern.
* `eval(some_quoted_expression)` without `parse()` — that's normal
  metaprogramming.
* `str2lang(x)` / `str2expression(x)` followed by `eval(...)` — same
  anti-idiom in disguise; flagged separately:
  `eval(str2lang(...))`, `eval(str2expression(...))`.

Suppression
-----------
Trailing `# eval-parse-ok` comment on the same line suppresses that
finding — use sparingly, e.g. for a knitr/rmarkdown chunk option
parser where the input is fully internal.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.R, *.r, *.Rmd, *.rmd, *.Rnw.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# eval(parse(...)) and friends. The `(?s)` lets `.` match newlines so
# we catch the (rare but real) multi-line spelling. We require a
# `text` keyword OR a string-expression starting char inside parse(...).
RE_EVAL_PARSE_TEXT = re.compile(
    r"(?s)\b(?:base::)?evalq?\s*\(\s*parse\s*\(\s*[^)]*?\btext\s*="
)
RE_EVAL_STR2LANG = re.compile(
    r"(?s)\b(?:base::)?evalq?\s*\(\s*str2(?:lang|expression)\s*\("
)

RE_SUPPRESS = re.compile(r"#\s*eval-parse-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out '...' and "..." string contents and trailing `#` comments,
    preserving column positions. R uses `#` for comments (no block
    comment syntax) and supports both single- and double-quoted strings
    with backslash escapes."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch == "'" or ch == '"' or ch == "`":
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string / backtick identifier
        if ch == "\\" and in_s in ('"', "'") and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == in_s:
            out.append(ch)
            in_s = None
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def scan_text(text: str) -> list[tuple[int, int, str, str]]:
    """Return [(line, col, kind, snippet), ...]. We scrub line-by-line
    for comment/string masking, then run multi-line regexes over the
    scrubbed concatenation so a call broken across lines is still found."""
    raw_lines = text.splitlines()
    suppressed = {i + 1 for i, l in enumerate(raw_lines) if RE_SUPPRESS.search(l)}
    scrubbed_lines = [strip_comments_and_strings(l) for l in raw_lines]
    # Build a flat string with newlines preserved so column offsets
    # can be mapped back to (line, col).
    flat = "\n".join(scrubbed_lines)

    # Precompute line-start offsets in the flat string.
    line_starts = [0]
    for l in scrubbed_lines:
        line_starts.append(line_starts[-1] + len(l) + 1)  # +1 for newline

    def offset_to_linecol(off: int) -> tuple[int, int]:
        # Binary search would be fine; linear is plenty for typical files.
        for ln, start in enumerate(line_starts):
            if start > off:
                return ln, off - line_starts[ln - 1] + 1
        return len(line_starts), off - line_starts[-1] + 1

    findings: list[tuple[int, int, str, str]] = []
    for kind, regex in (
        ("eval-parse-text", RE_EVAL_PARSE_TEXT),
        ("eval-str2lang", RE_EVAL_STR2LANG),
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
    suffixes = {".r", ".rmd", ".rnw"}
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

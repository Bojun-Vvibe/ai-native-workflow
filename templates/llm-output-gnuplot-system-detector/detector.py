#!/usr/bin/env python3
"""Detect gnuplot dynamic-shell sinks in LLM-generated `.gp`/`.plt`/`.gnuplot`.

Gnuplot script files frequently grow runtime-shell escapes when an LLM is
asked to "render the plot then convert to PNG", "list the data files in this
directory", or "embed today's hostname in the title". The two main sinks are:

  system("...")   - returns stdout of the shell command, no file write.
  `...`           - backtick form, equivalent to system() but inside strings.
  set print "|cmd"   - opens a shell pipe for `print` output (RCE if cmd is
                       built from a runtime variable).
  load "<expr>"   - loads a gnuplot script file at runtime; if the path is
                    user-derived it is the same RCE pattern as `do FILE` in
                    Perl: gnuplot reads & executes the file as gnuplot code.
  call "<expr>"   - same as load, but with positional arguments.
  eval(expr)      - evaluates a *string* as a gnuplot command (this is the
                    classic eval-of-a-string sink; the argument is a string
                    expression, not a literal).

This detector is single-pass, python3 stdlib only. It masks gnuplot line
comments (`# ...`) and the interiors of single- and double-quoted string
literals before regex matching, so a comment like `# don't use system()` or
a string like "see system() docs" does not trigger.

Sinks flagged (one per line, first match wins):
  system-call       `system("...")`  or `system(varexpr)`
  backtick-call     `` `...$var...` `` inside a string or top-level
  set-print-pipe    `set print "|..."`
  load-dynamic      `load <expr>` where <expr> is not a string literal-only
  call-dynamic      `call <expr>` where <expr> is not a string literal-only
  eval-string       `eval(...)` (any argument)

False-positives suppressed: `system` / `eval` / `load` / `call` appearing
inside `# ...` comments or inside `"..."` / `'...'` strings, the bareword
`load "static.gp"` (treated as static load) and `call "static.gp"` are NOT
flagged - we only flag when the argument contains an expression operator
(`.`, `+`, variable reference, function call) or is non-string.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

EXTS = {".gp", ".plt", ".gnu", ".gnuplot"}

# Patterns run on masked lines.
PATTERNS_SIMPLE: List[Tuple[str, "re.Pattern[str]"]] = [
    ("system-call",    re.compile(r"\bsystem\s*\(")),
    ("eval-string",    re.compile(r"\beval\s*\(")),
]

# `set print "|..."` opens a shell pipe; the `|` is inside the string, so we
# match against the raw line (after stripping any line comment).
SET_PRINT_PIPE_RE = re.compile(r"""\bset\s+print\s+["']\|""")

# load/call: only flag when the argument is dynamic.
# A "static" load is `load "literal.gp"` or `load 'literal.gp'` with NO
# concatenation operator before the closing quote.
LOAD_CALL_RE = re.compile(r"\b(load|call)\s+(\S.*)$")
# Backtick: `...` (gnuplot uses backticks for shell substitution).
BACKTICK_RE = re.compile(r"`[^`]+`")


def mask(src: str) -> str:
    """Blank comment bodies and string-literal interiors. Preserve newlines."""
    out: List[str] = []
    i, n = 0, len(src)
    in_str = False
    str_quote = ""
    while i < n:
        c = src[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == str_quote:
                in_str = False
                out.append(c)
                i += 1
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if c == "#":
            eol = src.find("\n", i)
            if eol == -1:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (eol - i))
                i = eol
            continue
        if c == '"' or c == "'":
            in_str = True
            str_quote = c
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_trailing_comment(line: str) -> str:
    """Return `line` with any `# ...` trailing comment removed, ignoring `#`
    that appears inside a single- or double-quoted string."""
    in_str = False
    q = ""
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == q:
                in_str = False
            i += 1
            continue
        if c == '"' or c == "'":
            in_str = True
            q = c
            i += 1
            continue
        if c == "#":
            return line[:i]
        i += 1
    return line


def _is_static_string_arg(arg: str) -> bool:
    """True if `arg` is a single literal-only quoted string (no concat)."""
    s = arg.strip()
    # strip trailing comment-equivalent (already masked, so trailing spaces)
    s = s.rstrip()
    if not s:
        return False
    if (s.startswith('"') and s.endswith('"') and len(s) >= 2) or (
        s.startswith("'") and s.endswith("'") and len(s) >= 2
    ):
        body = s[1:-1]
        # must not contain unescaped quote of same kind
        # and must not be the *start* of a concatenation: after masking,
        # the body of "..." is all spaces, so any '.' or '+' inside `s`
        # outside the quotes would mean s isn't purely a single string.
        # Since we already required s starts and ends with the quote and
        # checked length, the only way this fails is interior quote escape;
        # we're conservative and accept it.
        return True
    return False


def scan_file(path: str) -> List[Tuple[int, int, str, str]]:
    findings: List[Tuple[int, int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
        return findings
    masked = mask(src)
    masked_lines = masked.splitlines()
    raw_lines = src.splitlines()
    for idx, m in enumerate(masked_lines):
        hit = None
        for name, pat in PATTERNS_SIMPLE:
            mo = pat.search(m)
            if mo:
                hit = (idx + 1, mo.start() + 1, name)
                break
        if hit is None:
            mo = LOAD_CALL_RE.search(m)
            if mo:
                kind = mo.group(1)
                arg = mo.group(2)
                if not _is_static_string_arg(arg):
                    hit = (idx + 1, mo.start() + 1, f"{kind}-dynamic")
        if hit is None:
            # set print "|cmd" - the `|` lives inside the string, so check raw.
            raw = raw_lines[idx] if idx < len(raw_lines) else ""
            stripped = raw.lstrip()
            if not stripped.startswith("#"):
                # strip trailing line comment (best-effort: outside strings)
                code_only = _strip_trailing_comment(raw)
                mo = SET_PRINT_PIPE_RE.search(code_only)
                if mo:
                    hit = (idx + 1, mo.start() + 1, "set-print-pipe")
        if hit is None:
            # backtick: search original (un-masked) line so we catch
            # backticks even inside strings (gnuplot expands them inside
            # double-quoted strings).
            raw = raw_lines[idx] if idx < len(raw_lines) else ""
            # but skip if the whole line is a comment
            stripped = raw.lstrip()
            if not stripped.startswith("#"):
                mo = BACKTICK_RE.search(raw)
                if mo:
                    hit = (idx + 1, mo.start() + 1, "backtick-call")
        if hit is not None:
            lineno, col, name = hit
            snippet = raw_lines[idx].strip() if idx < len(raw_lines) else ""
            findings.append((lineno, col, name, snippet))
    return findings


def walk(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    if os.path.splitext(f)[1] in EXTS:
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def main(argv: List[str]) -> int:
    if not argv:
        print("usage: detector.py PATH [PATH ...]", file=sys.stderr)
        return 2
    total = 0
    for path in walk(argv):
        for lineno, col, name, snippet in scan_file(path):
            print(f"{path}:{lineno}:{col}: {name} {snippet}")
            total += 1
    print(f"-- {total} finding(s)", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""llm-output-python-django-mark-safe-detector.

Pure-stdlib single-pass line scanner that flags Python source where
Django's ``mark_safe(...)`` (or the equivalent ``SafeString(...)`` /
``format_html(...)``-with-non-literal-template / ``|safe`` filter
applied to user input) is invoked with an argument that is NOT a
bare string literal.

Marking attacker-controlled data as "safe" disables Django's
auto-escaping in templates and re-introduces XSS. LLMs reach for
``mark_safe`` because the tutorial they trained on shows it as the
fix for "the HTML is being escaped in the page" — without explaining
the threat model.

Detector only. Reports findings to stdout. Never executes input.

Usage:
    python3 detector.py <file-or-directory> [...]

Exit codes:
    0  no findings
    1  one or more findings
    2  usage error
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_OK_MARKER = "# mark-safe-ok"

# Calls we consider dangerous when their first argument is non-literal.
# Keyed by callable name (or attribute chain tail).
_DANGEROUS_CALLS = (
    "mark_safe",
    "SafeString",
    "SafeText",  # legacy alias
)

# Match a call site like `mark_safe(<arg...>)` (and capture from the
# opening paren onward so we can inspect the argument).
_CALL_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        name,
        re.compile(r"(?<![A-Za-z0-9_.])" + re.escape(name) + r"\s*\(\s*(?P<arg>.*)$"),
    )
    for name in _DANGEROUS_CALLS
]

# `|safe` filter applied to a non-literal template variable.
# Examples flagged: `{{ user_html|safe }}`, `{{ form.cleaned_data.bio|safe }}`
_SAFE_FILTER = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\|\s*safe\s*\}\}")

# Bare string literal first arg detection. We accept either:
#   'literal'                     # single-quoted, no interpolation
#   "literal"                     # double-quoted, no interpolation
#   '''literal'''  / """literal""" on the same line, no f-prefix
# Anything else (variables, f-strings, format(), %, +, function calls)
# is treated as non-literal => suspicious.
_BARE_SQ = re.compile(r"""^\s*'(?:[^'\\]|\\.)*'\s*[,)]""")
_BARE_DQ = re.compile(r'''^\s*"(?:[^"\\]|\\.)*"\s*[,)]''')
_BARE_TRIPLE_SQ = re.compile(r"""^\s*'''(?:(?!''').)*'''\s*[,)]""")
_BARE_TRIPLE_DQ = re.compile(r'''^\s*"""(?:(?!""").)*"""\s*[,)]''')

# f-string prefix (these are NOT bare even if quoted).
_F_STRING_HEAD = re.compile(r"""^\s*[fF]['"]""")


def _strip_inline_comment(line: str) -> str:
    """Drop inline `#` comments outside of single-line string literals."""
    out: List[str] = []
    in_str: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_str = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        if ch == "\\" and i + 1 < n:
            out.append(line[i + 1])
            i += 2
            continue
        if ch == in_str:
            in_str = None
        i += 1
    return "".join(out)


def _arg_is_bare_literal(arg: str) -> bool:
    """Return True iff ``arg`` (the text after the opening paren of the
    call, up to end-of-line) starts with a bare string literal that
    closes on the same logical token, with no f-prefix."""
    if _F_STRING_HEAD.match(arg):
        return False
    return bool(
        _BARE_TRIPLE_DQ.match(arg)
        or _BARE_TRIPLE_SQ.match(arg)
        or _BARE_DQ.match(arg)
        or _BARE_SQ.match(arg)
    )


def _iter_target_files(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                if os.path.basename(root).startswith("."):
                    continue
                for f in files:
                    if f.endswith((".py", ".html", ".htm", ".djhtml")):
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def scan_file(path: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    is_template = path.endswith((".html", ".htm", ".djhtml"))
    in_triple: str | None = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if _OK_MARKER in raw:
                    continue
                line_for_scan = raw

                if not is_template:
                    # Track multi-line triple-quoted strings (docstrings)
                    # in .py files so we don't flag examples inside them.
                    if in_triple is not None:
                        end = raw.find(in_triple)
                        if end == -1:
                            continue
                        in_triple = None
                        line_for_scan = raw[end + 3 :]
                    for delim in ('"""', "'''"):
                        first = line_for_scan.find(delim)
                        if first == -1:
                            continue
                        second = line_for_scan.find(delim, first + 3)
                        if second == -1:
                            in_triple = delim
                            line_for_scan = line_for_scan[:first]
                            break
                    code = _strip_inline_comment(line_for_scan)
                    for name, pat in _CALL_PATTERNS:
                        m = pat.search(code)
                        if not m:
                            continue
                        arg_tail = m.group("arg")
                        if _arg_is_bare_literal(arg_tail):
                            continue
                        findings.append(
                            (
                                lineno,
                                f"{name}() called with non-literal argument",
                                raw.rstrip("\n"),
                            )
                        )
                        break
                else:
                    # Template scan: only `|safe` filter on a variable.
                    for m in _SAFE_FILTER.finditer(raw):
                        var = m.group(1)
                        findings.append(
                            (
                                lineno,
                                f"|safe filter applied to template variable '{var}'",
                                raw.rstrip("\n"),
                            )
                        )
    except OSError as exc:
        print(f"warn: could not read {path}: {exc}", file=sys.stderr)
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__ or "", file=sys.stderr)
        return 2
    total = 0
    for fpath in _iter_target_files(argv[1:]):
        for lineno, label, snippet in scan_file(fpath):
            print(f"{fpath}:{lineno}: {label}: {snippet.strip()}")
            total += 1
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

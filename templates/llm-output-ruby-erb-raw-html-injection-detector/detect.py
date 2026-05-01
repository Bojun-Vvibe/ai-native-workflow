#!/usr/bin/env python3
"""
llm-output-ruby-erb-raw-html-injection-detector

Flags Ruby ERB / Rails view templates where user-controllable values
are emitted *unescaped* into HTML. In Rails ERB, the default ``<%= %>``
tag HTML-escapes its result through ``ERB::Util.html_escape``. Any of
the following undo that protection and reintroduce reflected/stored
XSS:

* ``<%= raw(...) %>`` and the bare ``raw ...`` form
* ``<%== ... %>`` (Rails ERB explicit-unescape tag)
* ``<%= ....html_safe %>`` on a value that was concatenated, sprintf'd,
  read from params/cookies/request, or from a model attribute
* ``<%= sanitize(...) %>`` is *not* flagged (sanitize whitelists tags)

Detector is intentionally conservative: it requires both an unescape
sink AND evidence the data is dynamic (not a literal string and not a
``t(...)``/``I18n.t`` call). Stdlib only. Exit 0 = clean, 1 = findings,
2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# ERB tag that emits without escaping. We capture the *inner* expression.
_RAW_TAG_RE = re.compile(r"<%==\s*(?P<expr>.*?)\s*%>", re.DOTALL)
# <%= raw(...) %> or <%= raw ... %>
_RAW_CALL_RE = re.compile(
    r"<%=\s*raw[\s(]+(?P<expr>.*?)[\s)]*%>", re.DOTALL
)
# <%= something.html_safe %>
_HTML_SAFE_RE = re.compile(
    r"<%=\s*(?P<expr>.+?)\.html_safe\b.*?%>", re.DOTALL
)

# Heuristics for "expression looks dynamic / user-derived".
_DYNAMIC_HINTS = (
    "params",
    "request.",
    "cookies",
    "session[",
    "env[",
    "@",          # instance var
    "#{",         # string interpolation
    " + ",        # string concat
    "format(",
    "sprintf(",
    ".to_s",
    ".join",
    "current_user",
    "flash[",
)

# An expression that is plainly a literal or i18n call -- not flagged.
# Deliberately NOT using DOTALL: a literal must not span concatenations.
_SAFE_EXPR_RE = re.compile(
    r"""^\s*(?:
        "[^"\n+#]*"                  # double-quoted literal, no concat / interp
        |'[^'\n+]*'                  # single-quoted literal, no concat
        |t\s*\([^)]*\)               # t("...")
        |I18n\.t\s*\([^)]*\)
        |\d+(?:\.\d+)?               # number
    )\s*$""",
    re.VERBOSE,
)

_SUFFIXES = (".erb", ".rhtml", ".html.erb", ".erb.txt")


def _is_dynamic(expr: str) -> bool:
    if _SAFE_EXPR_RE.match(expr):
        return False
    return any(h in expr for h in _DYNAMIC_HINTS)


def _scan_text(text: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def line_no(pos: int) -> int:
        # binary-search-lite; templates are small.
        ln = 1
        for start in line_starts:
            if start > pos:
                break
            ln_candidate = line_starts.index(start) + 1
            ln = ln_candidate
        return ln

    for label, regex in (
        ("erb-double-equals-unescape", _RAW_TAG_RE),
        ("erb-raw-call", _RAW_CALL_RE),
        ("erb-html-safe-on-dynamic", _HTML_SAFE_RE),
    ):
        for m in regex.finditer(text):
            expr = m.group("expr").strip()
            if label == "erb-html-safe-on-dynamic" and not _is_dynamic(expr):
                continue
            if label == "erb-raw-call" and not _is_dynamic(expr):
                # raw("literal") is harmless; require dynamic input.
                continue
            if label == "erb-double-equals-unescape" and not _is_dynamic(expr):
                continue
            findings.append((line_no(m.start()), label, expr[:120]))
    return findings


def _iter_files(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in files:
                    if name.endswith(_SUFFIXES):
                        yield os.path.join(root, name)
        else:
            yield p


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detect.py <file-or-dir> [more...]",
            file=sys.stderr,
        )
        return 2
    any_finding = False
    for path in _iter_files(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"{path}: read error: {exc}", file=sys.stderr)
            continue
        for line, label, snippet in _scan_text(text):
            any_finding = True
            print(f"{path}:{line}: {label}: {snippet}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

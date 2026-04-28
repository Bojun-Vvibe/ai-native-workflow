#!/usr/bin/env python3
"""Detect regex patterns prone to catastrophic backtracking (ReDoS).

LLMs frequently emit regexes with nested quantifiers like `(a+)+`, `(.*)*`,
or `(\\w+)+$` that trigger exponential matching time on adversarial input.
This detector scans Python, JavaScript, and Go-style source files for
string literals passed to regex APIs (`re.compile`, `re.match`, `re.search`,
`re.findall`, `re.sub`, `new RegExp`, `regexp.MustCompile`, etc.) and runs
a set of structural checks against each extracted pattern.

It also accepts raw `.txt` files containing one pattern per line (lines
beginning with `#` are ignored).

Stdlib only. Does not execute regexes against any input. Always exits 0.
"""

from __future__ import annotations

import re
import sys
from typing import Iterator, List, Tuple


# --- pattern extraction ---------------------------------------------------

# Match callsites like re.compile("..."), re.search(r'...'), new RegExp("..."),
# regexp.MustCompile(`...`). We intentionally support single, double, and
# (for Go) backtick-delimited literals.
CALLSITE_RE = re.compile(
    r"""
    (?P<api>
        \bre\.(?:compile|match|search|findall|finditer|fullmatch|split|sub|subn)
      | \bnew\s+RegExp
      | \bregexp\.(?:MustCompile|Compile)
    )
    \s*\(\s*
    (?:[rRuUbB]{1,2})?
    (?P<quote>['"`])
    (?P<pat>(?:\\.|(?!(?P=quote)).)*)
    (?P=quote)
    """,
    re.VERBOSE,
)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _extract_from_source(text: str) -> Iterator[Tuple[int, str, str]]:
    """Yield (lineno, api, pattern_string) from source-style files."""
    for m in CALLSITE_RE.finditer(text):
        yield _line_of(text, m.start("pat")), m.group("api"), m.group("pat")


def _extract_from_txt(text: str) -> Iterator[Tuple[int, str, str]]:
    """Yield (lineno, '<txt>', pattern_string) from one-per-line files."""
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.rstrip("\n")
        if not s.strip() or s.lstrip().startswith("#"):
            continue
        yield i, "<txt>", s


# --- danger checks --------------------------------------------------------

# (X)+, (X)*, (X){n,} where X itself contains an unbounded quantifier.
# We approximate by scanning groups for inner +/*/{n,} followed by a
# closing-paren-then-quantifier.
NESTED_QUANT_RE = re.compile(
    r"""
    \(                              # opening group
      (?:[^()\\]|\\.)*              # body without nested parens
      [+*]                          # inner unbounded quant OR
      (?:[?]?)                      # optional lazy
      (?:[^()\\]|\\.)*
    \)
    \s*
    (?:[+*]|\{\d+,\d*\})            # outer unbounded quant
    """,
    re.VERBOSE,
)

# Alternation with overlapping subjects e.g. (a|a|aa)+ or (\\w|\\w+)+
ALT_QUANT_RE = re.compile(
    r"""
    \(
      (?:[^()|\\]|\\.)+
      \|
      (?:[^()\\]|\\.)+
    \)
    \s*[+*]
    """,
    re.VERBOSE,
)

# Patterns like (.*)*, (.+)+, (.*)+, (.+)*
DOTSTAR_NEST_RE = re.compile(r"\(\s*\.\s*[*+]\s*\)\s*[*+]")

# Trailing anchored greedy quantifier on \w/\S/. e.g. (\w+)+$ — classic
# evil-regex shape.
TRAIL_ANCHOR_RE = re.compile(
    r"""
    \(
      \\?[wWsSdD.]
      [+*]
    \)
    \s*[+*]
    \s*\$
    """,
    re.VERBOSE,
)


def check_pattern(pat: str) -> List[Tuple[str, str]]:
    """Return list of (code, message) findings for a single pattern."""
    out: List[Tuple[str, str]] = []
    if DOTSTAR_NEST_RE.search(pat):
        out.append(("REDOS001", "nested unbounded quantifier on '.' (e.g. (.*)*)"))
    if NESTED_QUANT_RE.search(pat):
        out.append(("REDOS002", "nested quantifier in group (e.g. (a+)+, (\\w*)+)"))
    if ALT_QUANT_RE.search(pat):
        out.append(("REDOS003", "alternation with overlap under quantifier (e.g. (a|aa)+)"))
    if TRAIL_ANCHOR_RE.search(pat):
        out.append(("REDOS004", "trailing anchored greedy class (e.g. (\\w+)+$)"))
    # Validity check: still try to compile; if it doesn't compile we note it
    # as a soft finding so callers know the pattern is broken anyway.
    try:
        re.compile(pat)
    except re.error as e:
        out.append(("REDOS000", f"pattern does not compile: {e}"))
    return out


# --- driver ---------------------------------------------------------------

def _looks_like_source(path: str) -> bool:
    return path.lower().endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rb"))


def scan(path: str, text: str) -> int:
    if path == "<stdin>" or _looks_like_source(path):
        items = list(_extract_from_source(text))
        if not items and not _looks_like_source(path):
            items = list(_extract_from_txt(text))
    else:
        items = list(_extract_from_txt(text))

    findings = 0
    for lineno, api, pat in items:
        for code, msg in check_pattern(pat):
            print(f"{path}:{lineno}: {code}: {msg} | api={api} pattern={pat!r}")
            findings += 1
    print(f"# findings: {findings}")
    return findings


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path|->...", file=sys.stderr)
        print("# findings: 0")
        return 0
    for p in argv[1:]:
        display = p if p != "-" else "<stdin>"
        try:
            text = _read(p)
        except OSError as e:
            print(f"{display}: ERROR: {e}", file=sys.stderr)
            continue
        scan(display, text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

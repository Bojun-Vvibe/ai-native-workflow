#!/usr/bin/env python3
"""Detect ``eval`` / ``Function`` / ``vm.run*`` invocations in
LLM-emitted Node.js / browser JavaScript whose first argument is NOT
a bare string literal.

See README.md for full description, CWE references, and limitations.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// eval-user-input-ok"

EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}

# Match the call site. We capture the kind so we can report it.
_CALL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "eval",
        re.compile(r"(?<![A-Za-z0-9_$.])(?:window\.|global\.|globalThis\.)?eval\s*\("),
    ),
    (
        "new-Function",
        re.compile(r"\bnew\s+Function\s*\("),
    ),
    (
        "Function-call",
        re.compile(r"(?<![A-Za-z0-9_$.])Function\s*\("),
    ),
    (
        "vm.runInNewContext",
        re.compile(r"\bvm\s*\.\s*runInNewContext\s*\("),
    ),
    (
        "vm.runInThisContext",
        re.compile(r"\bvm\s*\.\s*runInThisContext\s*\("),
    ),
    (
        "vm.runInContext",
        re.compile(r"\bvm\s*\.\s*runInContext\s*\("),
    ),
    (
        "vm.compileFunction",
        re.compile(r"\bvm\s*\.\s*compileFunction\s*\("),
    ),
    (
        "vm.Script",
        re.compile(r"\b(?:new\s+)?vm\s*\.\s*Script\s*\("),
    ),
]

# Bare string literal first arg: '...' or "..." with no interpolation.
RE_BARE_QSTRING = re.compile(
    r"""
    \(\s*
    (?P<q>'|\")
    (?:(?!(?P=q)).)*
    (?P=q)
    \s*[,)]
    """,
    re.VERBOSE,
)

# Bare template literal first arg: `...` with NO ${...} inside.
RE_BARE_TEMPLATE = re.compile(
    r"""
    \(\s*
    `
    (?:(?!\$\{)[^`])*
    `
    \s*[,)]
    """,
    re.VERBOSE,
)

# `new Function("a", "b", "code")` — all args are bare string literals.
RE_BARE_QSTRING_LIST = re.compile(
    r"""
    \(\s*
    (?:
        (?P<q>'|\")
        (?:(?!(?P=q)).)*
        (?P=q)
        \s*(?:,\s*)?
    )+
    \s*\)
    """,
    re.VERBOSE,
)


def _strip_comments_and_strings(line: str) -> str:
    """Drop // and /* */ on this line; mask strings/templates as spaces.

    Preserves length so positions are stable.
    """
    out: list[str] = []
    i = 0
    in_s = False
    quote = ""
    in_block_comment = False
    while i < len(line):
        ch = line[i]
        nxt = line[i + 1] if i + 1 < len(line) else ""
        if in_block_comment:
            if ch == "*" and nxt == "/":
                out.append("  ")
                i += 2
                in_block_comment = False
                continue
            out.append(" ")
            i += 1
            continue
        if in_s:
            if ch == "\\" and nxt:
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                in_s = False
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if ch == "/" and nxt == "/":
            break  # rest of line is comment
        if ch == "/" and nxt == "*":
            in_block_comment = True
            out.append("  ")
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_s = True
            quote = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _arg_is_bare_literal_at(raw_line: str, paren_idx: int, kind: str) -> bool:
    """Return True if the first arg starting at ``paren_idx`` is a bare literal.

    For ``new-Function`` / ``Function-call`` we also accept a list of
    multiple bare-string args (the legitimate ``new Function('a','b','code')``
    form), because ALL args being literal means no interpolation.
    """
    sub = raw_line[paren_idx:]
    if RE_BARE_QSTRING.match(sub):
        return True
    if RE_BARE_TEMPLATE.match(sub):
        return True
    if kind in ("new-Function", "Function-call") and RE_BARE_QSTRING_LIST.match(sub):
        return True
    return False


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        line = _strip_comments_and_strings(raw)
        seen_at: set[int] = set()
        for kind, pat in _CALL_PATTERNS:
            for m in pat.finditer(line):
                paren_idx = m.end() - 1
                if paren_idx in seen_at:
                    continue
                # Use the ORIGINAL raw line for arg classification so
                # the literal contents are visible.
                if not _arg_is_bare_literal_at(raw, paren_idx, kind):
                    findings.append(
                        (path, lineno, f"{kind}-non-literal-arg", raw.rstrip())
                    )
                    seen_at.add(paren_idx)
                    # Don't break — multiple distinct calls could appear
                    # on one line, but mark this paren handled.
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix in EXTS:
                    out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

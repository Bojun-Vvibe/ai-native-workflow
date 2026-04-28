#!/usr/bin/env python3
"""Detect Swift force-unwrap (`!`), forced cast (`as!`), and implicitly
unwrapped optional declarations in Swift source files.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# `try!` keyword.
RE_TRY_BANG = re.compile(r"\btry!")
# Forced cast: `as!`.
RE_AS_BANG = re.compile(r"\bas!")
# Implicitly unwrapped optional in a declaration:
#   var name: Type!     let name: Type!     var name: [Foo]!
RE_IUO_DECL = re.compile(
    r"\b(?:var|let)\s+[A-Za-z_]\w*\s*:\s*[A-Za-z_][\w.<>\[\] ,?]*!"
)
# Force-unwrap after an identifier, subscript, or call: `foo!`, `a.b!`,
# `dict[k]!`, `f()!`. Followed by something that is NOT `=` (so we skip `!=`).
RE_FORCE_UNWRAP = re.compile(r"([A-Za-z_]\w*|\)|\])!(?!=)")


def _strip_strings_and_comment(line: str) -> str:
    """Blank out double-quoted string literals and any trailing `//` comment
    so `!` inside them is ignored. Crude but enough for line-based linting."""
    out = []
    i = 0
    n = len(line)
    in_str = False
    while i < n:
        ch = line[i]
        if not in_str and ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        if ch == '"':
            in_str = not in_str
            out.append('"')
        elif in_str:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            out.append(" ")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        scrub = _strip_strings_and_comment(raw)
        for m in RE_TRY_BANG.finditer(scrub):
            findings.append((path, lineno, m.start() + 1, "try-bang", raw.strip()))
        for m in RE_AS_BANG.finditer(scrub):
            findings.append((path, lineno, m.start() + 1, "forced-cast", raw.strip()))
        for m in RE_IUO_DECL.finditer(scrub):
            findings.append((path, lineno, m.start() + 1, "iuo-decl", raw.strip()))
        # Track columns already claimed by try!/as!/iuo so force-unwrap
        # doesn't double-report them.
        claimed = set()
        for m in RE_TRY_BANG.finditer(scrub):
            claimed.add(m.end())  # position of the `!`
        for m in RE_AS_BANG.finditer(scrub):
            claimed.add(m.end())
        for m in RE_IUO_DECL.finditer(scrub):
            claimed.add(m.end())
        for m in RE_FORCE_UNWRAP.finditer(scrub):
            bang_pos = m.end()  # 1-based-ish column of the `!` end
            if bang_pos in claimed:
                continue
            findings.append(
                (path, lineno, bang_pos, "force-unwrap", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*.swift")):
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
            print(f"{f_path}:{line}:{col}: {kind} — {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

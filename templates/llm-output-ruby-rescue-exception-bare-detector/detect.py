#!/usr/bin/env python3
"""Detect Ruby `rescue Exception`, empty bare-rescue blocks, and inline
`expr rescue value` forms.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments_and_strings(line: str) -> str:
    """Blank out '...' / "..." string contents and trailing '#' comments,
    preserving column positions. Crude but enough for line-based linting."""
    out = []
    i = 0
    n = len(line)
    in_s = None  # None | "'" | '"'
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "#":
                # rest of line is comment
                out.append(" " * (n - i))
                break
            if ch == "'" or ch == '"':
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside string
        if ch == "\\" and i + 1 < n:
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


# `rescue Exception` (optionally `=> e`, optionally other classes alongside).
RE_RESCUE_EXCEPTION = re.compile(r"\brescue\b[^#\n]*?\bException\b")
# Header of a bare rescue (no class list). Matches `rescue` at end of
# statement, `rescue =>`, `rescue then`, `rescue` followed by EOL.
RE_BARE_RESCUE_HEADER = re.compile(
    r"(^|\s)rescue\s*(=>\s*[A-Za-z_]\w*\s*)?(then\b|$)"
)
# Inline form: <something> rescue <something>.
# We require non-space before `rescue` on the same line and non-end-of-line
# after it, AND the line must not be a header-style bare rescue (which would
# start with optional whitespace + `rescue`).
RE_INLINE_RESCUE = re.compile(r"\S\s+rescue\s+\S")


def is_block_terminator(stripped: str) -> bool:
    return (
        stripped.startswith("end")
        or stripped.startswith("rescue")
        or stripped.startswith("ensure")
        or stripped.startswith("else")
        or stripped == ""
    )


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    raw_lines = raw.splitlines()
    scrubbed = [strip_comments_and_strings(l) for l in raw_lines]

    for idx, scrub in enumerate(scrubbed):
        lineno = idx + 1
        # 1) rescue Exception
        for m in RE_RESCUE_EXCEPTION.finditer(scrub):
            findings.append(
                (path, lineno, m.start() + 1, "rescue-exception", raw_lines[idx].strip())
            )
        # 2) bare-rescue with empty / trivial body
        for m in RE_BARE_RESCUE_HEADER.finditer(scrub):
            # Skip if this header actually contains `Exception` (handled above).
            header_seg = scrub[m.start() : ].split("\n", 1)[0]
            if "Exception" in header_seg:
                continue
            # Look at next non-blank lines until terminator; allow only:
            #   nothing, "nil", "false", "next", or pure comment lines (already blanked)
            j = idx + 1
            body_lines = []
            while j < len(scrubbed):
                s = scrubbed[j].strip()
                if is_block_terminator(s):
                    break
                if s:
                    body_lines.append(s)
                j += 1
            trivial = all(b in ("nil", "false", "next", "next nil", "return", "return nil") for b in body_lines)
            if trivial:
                findings.append(
                    (
                        path,
                        lineno,
                        m.start() + (1 if m.group(1) == "" else 2),
                        "bare-rescue-empty",
                        raw_lines[idx].strip(),
                    )
                )
        # 3) inline rescue `expr rescue value` — but only if the line is
        # NOT itself a header-style bare rescue (which starts with whitespace
        # then `rescue`).
        line_lstrip = scrub.lstrip()
        if not line_lstrip.startswith("rescue"):
            for m in RE_INLINE_RESCUE.finditer(scrub):
                # Avoid double-reporting a `rescue Exception` on the same line.
                if "Exception" in scrub[m.start() : m.start() + 40]:
                    continue
                findings.append(
                    (
                        path,
                        lineno,
                        m.start() + 1,
                        "inline-bare-rescue",
                        raw_lines[idx].strip(),
                    )
                )
                break  # one finding per line is enough
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*.rb")):
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

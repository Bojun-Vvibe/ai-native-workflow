#!/usr/bin/env python3
"""llm-output-slurm-auth-none-detector

Flag Slurm `slurm.conf` files that set `AuthType=auth/none` (or the
synonym `AuthType=none`), which disables RPC authentication.
"""

from __future__ import annotations

import re
import sys

USAGE = "usage: detect.py <slurm.conf|->\n"

# Match lines like:
#   AuthType=auth/none
#   authtype = auth/none
#   AuthType= none
# but not commented lines.
PATTERN = re.compile(
    r"""^\s*                # leading whitespace
        authtype            # the key (case-insensitive via flags)
        \s*=\s*             # equals with optional spaces
        (auth/none|none)    # insecure values
        \s*(?:\#.*)?$       # optional trailing comment
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_comment(line: str) -> str:
    """Remove a `#` line comment, preserving the prefix."""
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote:
            return line[:i]
    return line


def scan(text: str, path: str) -> list[str]:
    findings: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        # Drop comment-only lines fast.
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        body = strip_comment(raw)
        if PATTERN.match(body):
            findings.append(
                f"{path}:{lineno}: insecure Slurm AuthType "
                f"(disables RPC auth): {raw.strip()}"
            )
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(USAGE)
        return 2
    src = argv[1]
    if src == "-":
        text = sys.stdin.read()
        path = "<stdin>"
    else:
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            sys.stderr.write(f"cannot read: {src}: {exc}\n")
            return 2
        path = src
    findings = scan(text, path)
    if findings:
        for f in findings:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

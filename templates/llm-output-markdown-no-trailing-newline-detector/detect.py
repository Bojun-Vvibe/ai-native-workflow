#!/usr/bin/env python3
"""Detect Markdown files that lack exactly one trailing newline.

Flags two failure modes common in LLM-streamed output:
  - file does not end with any newline (most common — stream stopped mid-token)
  - file ends with multiple blank lines (extra \\n\\n... at EOF)

Exit codes:
  0 = file ends with exactly one trailing newline (or is empty)
  1 = trailing-newline violation
  2 = usage / IO error
"""
from __future__ import annotations

import sys
from pathlib import Path


def check(data: bytes) -> str | None:
    """Return None if OK, else a human-readable reason string."""
    if len(data) == 0:
        return None  # empty file is fine

    # Accept \r\n as a proper single terminator
    if data.endswith(b"\r\n"):
        # Check for multiple CRLFs at end
        n = 0
        i = len(data)
        while i >= 2 and data[i - 2 : i] == b"\r\n":
            n += 1
            i -= 2
        if n >= 2:
            return f"file ends with {n} trailing CRLF newlines (expected exactly 1)"
        return None

    if not data.endswith(b"\n"):
        # Last char is content
        last = data[-1:].decode("utf-8", errors="replace")
        return f"file does not end with a newline (last byte: {last!r})"

    # Ends with at least one \n — count trailing \n
    n = 0
    i = len(data)
    while i > 0 and data[i - 1 : i] == b"\n":
        n += 1
        i -= 1
    if n >= 2:
        return f"file ends with {n} trailing newlines (expected exactly 1)"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file.md>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    reason = check(data)
    if reason is None:
        return 0

    print(f"{path}: trailing-newline: {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

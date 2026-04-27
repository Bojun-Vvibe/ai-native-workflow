#!/usr/bin/env python3
"""Detect ambiguous nested fences using the same backtick/tilde count.

When a fenced code block opens with N backticks and contains an inner
line of exactly N backticks, the inner line *closes* the outer block.
If a subsequent block of the same length re-opens, the visible
fingerprint is opener -> "closer" -> opener, all at the same length and
same indentation. This is the LLM-output failure mode the lens detects.

Stdlib only.

Usage:
    python3 detector.py FILE [FILE ...]

Exit codes:
    0  clean
    1  ambiguous nested fence found
    2  usage / IO error
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})\s*(?P<info>.*)$")


def fence_info(line: str):
    m = FENCE_RE.match(line)
    if not m:
        return None
    fence = m.group("fence")
    return {
        "indent": len(m.group("indent")),
        "char": fence[0],
        "len": len(fence),
        "info": m.group("info").rstrip(),
    }


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}: cannot read: {exc}", file=sys.stderr)
        return ["__io__"]

    lines = text.splitlines()
    findings: list[str] = []

    # Pass 1: parse fences with a 1-deep state machine, recording each block.
    blocks: list[dict] = []  # {open_line, close_line, indent, char, len, info}
    in_block = False
    cur: dict = {}
    for idx, line in enumerate(lines, start=1):
        info = fence_info(line)
        if not in_block:
            if info is not None:
                in_block = True
                cur = {
                    "open_line": idx,
                    "indent": info["indent"],
                    "char": info["char"],
                    "len": info["len"],
                    "info": info["info"],
                }
        else:
            # Inside a block: a closer must be same char, len >= opener len,
            # and have NO info string (CommonMark closer rule).
            if (
                info is not None
                and info["char"] == cur["char"]
                and info["len"] >= cur["len"]
                and info["info"] == ""
            ):
                cur["close_line"] = idx
                blocks.append(cur)
                in_block = False
                cur = {}
    if in_block:
        # Unclosed; record so we can still inspect, but don't flag here.
        cur["close_line"] = None
        blocks.append(cur)

    # Pass 2: look for opener -> closer -> opener of same (char, len, indent),
    # which is the textual fingerprint of an unintended nested-fence collapse.
    for i in range(len(blocks) - 1):
        a = blocks[i]
        b = blocks[i + 1]
        if a.get("close_line") is None:
            continue
        if (
            a["char"] == b["char"]
            and a["len"] == b["len"]
            and a["indent"] == b["indent"]
        ):
            # Heuristic: only flag when the gap between a's close and b's open
            # is small (<=3 lines), which matches the "inner fence accidentally
            # closed me" pattern rather than two unrelated blocks.
            gap = b["open_line"] - a["close_line"]
            if 1 <= gap <= 3:
                findings.append(
                    f"{path}:{a['open_line']}:{a['indent'] + 1}: "
                    f"ambiguous nested fence: opener of {a['len']} {a['char']!r} "
                    f"at line {a['open_line']} is closed at line {a['close_line']} "
                    f"and a same-length opener follows at line {b['open_line']}; "
                    f"raise outer fence to {a['len'] + 1} {a['char']!r} or use a "
                    f"different fence character for the inner block"
                )
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py FILE [FILE ...]", file=sys.stderr)
        return 2
    rc = 0
    for arg in argv[1:]:
        results = scan(Path(arg))
        if results == ["__io__"]:
            rc = max(rc, 2)
            continue
        for line in results:
            print(line)
        if results:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))

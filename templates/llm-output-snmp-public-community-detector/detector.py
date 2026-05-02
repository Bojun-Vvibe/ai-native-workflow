#!/usr/bin/env python3
"""Detect SNMP daemon configuration that uses the default ``public`` /
``private`` community strings.

See README.md for full rationale and CWE references.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*snmp-public-allowed")

# NET-SNMP forms:
#   rocommunity  <community> [source [oid [view]]]
#   rocommunity6 <community> [source [oid [view]]]
#   rwcommunity  <community> [source [oid [view]]]
#   rwcommunity6 <community> [source [oid [view]]]
RO_RE = re.compile(r"^\s*rocommunity6?\s+(\S+)", re.IGNORECASE)
RW_RE = re.compile(r"^\s*rwcommunity6?\s+(\S+)", re.IGNORECASE)

# Legacy mapping form:
#   com2sec <name> <source> <community>
COM2SEC_RE = re.compile(r"^\s*com2sec6?\s+\S+\s+\S+\s+(\S+)", re.IGNORECASE)

# Generic / embedded form:
#   community <name>            (Cisco IOS-style "snmp-server community public RO")
SNMP_SERVER_RE = re.compile(
    r"^\s*snmp-server\s+community\s+(\S+)", re.IGNORECASE
)
PLAIN_COMMUNITY_RE = re.compile(r"^\s*community\s+(\S+)", re.IGNORECASE)

DEFAULT_RO_NAMES = {"public"}
DEFAULT_RW_NAMES = {"private"}
ALL_DEFAULTS = DEFAULT_RO_NAMES | DEFAULT_RW_NAMES


def _strip_comment(line: str) -> str:
    # SNMP config uses '#' for comments; we only want the directive.
    if "#" in line:
        # but keep '#' inside quoted community names? SNMP communities
        # can't contain '#' meaningfully — strip everything after.
        line = line.split("#", 1)[0]
    return line


def scan(text: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if any(SUPPRESS.search(l) for l in text.splitlines()):
        return findings

    for idx, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line.strip():
            continue

        m = RO_RE.match(line)
        if m and m.group(1).lower() in DEFAULT_RO_NAMES:
            findings.append((idx, f"rocommunity uses default '{m.group(1)}'"))
            continue

        m = RW_RE.match(line)
        if m and m.group(1).lower() in DEFAULT_RW_NAMES:
            findings.append((idx, f"rwcommunity uses default '{m.group(1)}'"))
            continue

        m = COM2SEC_RE.match(line)
        if m and m.group(1).lower() in ALL_DEFAULTS:
            findings.append(
                (idx, f"com2sec maps to default community '{m.group(1)}'")
            )
            continue

        m = SNMP_SERVER_RE.match(line)
        if m and m.group(1).lower() in ALL_DEFAULTS:
            findings.append(
                (idx, f"snmp-server community uses default '{m.group(1)}'")
            )
            continue

        m = PLAIN_COMMUNITY_RE.match(line)
        if m and m.group(1).lower() in ALL_DEFAULTS:
            findings.append(
                (idx, f"community directive uses default '{m.group(1)}'")
            )
            continue

    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path> [<path> ...]", file=sys.stderr)
        return 0
    bad_files = 0
    for arg in argv[1:]:
        p = Path(arg)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"{p}:0:cannot read: {exc}", file=sys.stderr)
            continue
        hits = scan(text)
        if hits:
            bad_files += 1
            for ln, reason in hits:
                print(f"{p}:{ln}:{reason}")
    return min(bad_files, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

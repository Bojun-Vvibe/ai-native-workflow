#!/usr/bin/env python3
"""Detect Info.plist entries that disable / weaken App Transport Security.
CWE-319: cleartext transmission of sensitive information."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# We do NOT use plistlib here on purpose: many LLM-emitted snippets are
# fragments or have minor XML errors. A token-pair scan is more forgiving and
# is exactly the cheap-first-filter posture of the rest of the template family.

KEY_RE = re.compile(r"<key>\s*([A-Za-z0-9_]+)\s*</key>")
BOOL_RE = re.compile(r"<(true|false)\s*/>", re.IGNORECASE)
STRING_RE = re.compile(r"<string>\s*([^<]+?)\s*</string>")

GLOBAL_KEYS = {
    "NSAllowsArbitraryLoads": "ats-allows-arbitrary-loads",
    "NSAllowsArbitraryLoadsForMedia": "ats-allows-arbitrary-loads-media",
    "NSAllowsArbitraryLoadsInWebContent": "ats-allows-arbitrary-loads-web",
    "NSAllowsLocalNetworking": "ats-allows-local-networking",
}

EXCEPTION_BOOL_KEYS = {
    "NSExceptionAllowsInsecureHTTPLoads": "ats-exception-allows-insecure",
    "NSThirdPartyExceptionAllowsInsecureHTTPLoads": "ats-exception-allows-insecure",
}

WEAK_TLS = {"TLSv1.0", "TLSv1.1"}
TLS_KEYS = {
    "NSExceptionMinimumTLSVersion",
    "NSThirdPartyExceptionMinimumTLSVersion",
}


def scan_plist(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    if text.startswith("bplist"):
        return findings  # binary plist, skip
    lines = text.splitlines()
    n = len(lines)
    # Walk line-by-line; for any <key>X</key> look at the next non-blank line
    # for its value.
    for i, line in enumerate(lines):
        m = KEY_RE.search(line)
        if not m:
            continue
        key = m.group(1)
        # locate next non-blank line
        j = i + 1
        while j < n and not lines[j].strip():
            j += 1
        if j >= n:
            continue
        value_line = lines[j]
        bool_m = BOOL_RE.search(value_line)
        str_m = STRING_RE.search(value_line)
        line_no = i + 1
        snippet = line.strip()

        if key in GLOBAL_KEYS:
            if bool_m and bool_m.group(1).lower() == "true":
                findings.append((path, line_no, GLOBAL_KEYS[key], snippet))
        elif key in EXCEPTION_BOOL_KEYS:
            if bool_m and bool_m.group(1).lower() == "true":
                findings.append((path, line_no, EXCEPTION_BOOL_KEYS[key], snippet))
        elif key in TLS_KEYS:
            if str_m and str_m.group(1) in WEAK_TLS:
                findings.append((path, line_no, "ats-exception-min-tls-low", snippet))
    return findings


def walk(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.endswith(".plist"):
                yield Path(dirpath) / name


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <path>", file=sys.stderr)
        return 2
    root = Path(argv[1])
    if not root.exists():
        print(f"no such path: {root}", file=sys.stderr)
        return 2
    all_findings: list[tuple[Path, int, str, str]] = []
    for f in walk(root):
        all_findings.extend(scan_plist(f))
    for path, line_no, rule, snippet in all_findings:
        print(f"{path}:{line_no}:{rule}: {snippet}")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

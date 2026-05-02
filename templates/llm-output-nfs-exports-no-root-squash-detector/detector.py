#!/usr/bin/env python3
"""Detect NFS ``/etc/exports`` lines that combine ``no_root_squash``
with a wide client spec.

See README.md for the threat model and CWE references.

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

SUPPRESS = re.compile(r"#\s*nfs-no-root-squash-allowed")

# An exports line:
#   <path> <client>(<opts>) [<client>(<opts>) ...]
# `path` may be quoted or contain '\NNN' octal escapes; we only need
# to peel it off, then iterate client(opts) tokens.

CLIENT_OPTS_RE = re.compile(r"(\S+?)\(([^)]*)\)")

LOOPBACK = {"127.0.0.1", "localhost", "::1", "ip6-localhost"}
WIDE_LITERALS = {"*", "0.0.0.0", "0.0.0.0/0", "::", "::/0"}


def _client_is_wide(client: str) -> bool:
    c = client.strip()
    if not c:
        return False
    if c in LOOPBACK:
        return False
    if c in WIDE_LITERALS:
        return True
    # Wildcard hostnames: '*.example.com', '*' anywhere — flag.
    if c.startswith("*"):
        return True
    # CIDR: split on '/'
    if "/" in c:
        addr, _, prefix = c.partition("/")
        try:
            p = int(prefix)
        except ValueError:
            return False
        if ":" in addr:  # IPv6
            return p <= 32
        return p <= 16
    return False


def _strip_path(line: str) -> str:
    """Drop the export path token, return the remainder (clients+opts)."""
    s = line.strip()
    if s.startswith('"'):
        end = s.find('"', 1)
        if end == -1:
            return ""
        return s[end + 1 :].strip()
    # Unquoted: path runs until whitespace.
    parts = s.split(None, 1)
    if len(parts) < 2:
        return ""
    return parts[1]


def scan(text: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if any(SUPPRESS.search(l) for l in text.splitlines()):
        return findings

    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rest = _strip_path(line)
        if not rest:
            continue

        for m in CLIENT_OPTS_RE.finditer(rest):
            client, opts_raw = m.group(1), m.group(2)
            opts = {o.strip() for o in opts_raw.split(",") if o.strip()}

            wide = _client_is_wide(client)
            if not wide:
                continue

            if "no_root_squash" in opts:
                findings.append(
                    (
                        idx,
                        f"no_root_squash exported to wide client '{client}'",
                    )
                )
                continue

            if "no_all_squash" in opts and "insecure" in opts:
                findings.append(
                    (
                        idx,
                        (
                            "no_all_squash+insecure exported to wide "
                            f"client '{client}'"
                        ),
                    )
                )

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

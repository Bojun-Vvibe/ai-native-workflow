#!/usr/bin/env python3
"""Detect nginx ``ssl_protocols`` directives that enable deprecated
TLS protocol versions (SSLv2, SSLv3, TLSv1, TLSv1.1) on a TLS-enabled
server block.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

LEGACY_PROTOCOLS = {"SSLv2", "SSLv3", "TLSv1", "TLSv1.1"}

SSL_PROTOCOLS_RE = re.compile(
    r"^\s*ssl_protocols\s+([^;#]+);",
    re.IGNORECASE,
)
LISTEN_SSL_RE = re.compile(
    r"^\s*listen\s+[^;#]*\b(?:ssl|quic)\b",
    re.IGNORECASE,
)
SUPPRESS_RE = re.compile(r"#\s*llm-tls-legacy-ok\b", re.IGNORECASE)


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def _tokenize_blocks(source: str) -> List[Tuple[int, int, int]]:
    """Return list of (start_line, end_line, depth_at_start) for each
    ``server { ... }`` block found in source. Depth tracking is naive
    but adequate for nginx-style configs without quoted braces.
    """
    server_blocks: List[Tuple[int, int, int]] = []
    lines = source.splitlines()
    # Map char position to line number via scanning.
    # We instead scan token-by-token character-wise.
    depth = 0
    in_server_stack: List[Tuple[int, int]] = []  # (start_line, depth_at_open)
    i = 0
    n = len(source)
    line_no = 1
    # Pre-scan to detect "server" keyword occurrences before '{'.
    # We iterate char-by-char, remembering the most recent identifier
    # before each '{'.
    last_ident_start = -1
    last_ident_end = -1
    cur_ident_start = -1
    while i < n:
        c = source[i]
        if c == "\n":
            line_no += 1
            i += 1
            continue
        if c == "#":
            # skip rest of line
            j = source.find("\n", i)
            if j == -1:
                break
            i = j
            continue
        if c.isalnum() or c == "_":
            if cur_ident_start == -1:
                cur_ident_start = i
            i += 1
            continue
        else:
            if cur_ident_start != -1:
                last_ident_start = cur_ident_start
                last_ident_end = i
                cur_ident_start = -1
            if c == "{":
                ident = source[last_ident_start:last_ident_end] if last_ident_start != -1 else ""
                depth += 1
                if ident == "server":
                    in_server_stack.append((line_no, depth))
                i += 1
                continue
            if c == "}":
                if in_server_stack and in_server_stack[-1][1] == depth:
                    start_line, d = in_server_stack.pop()
                    server_blocks.append((start_line, line_no, d))
                depth -= 1
                i += 1
                continue
            i += 1
    return server_blocks


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    lines = source.splitlines()
    server_blocks = _tokenize_blocks(source)

    # Determine which server blocks are TLS-enabled (have a `listen ... ssl`).
    tls_blocks: List[Tuple[int, int]] = []
    for start, end, _ in server_blocks:
        for ln in range(start, end + 1):
            if ln - 1 >= len(lines):
                break
            stripped = _strip_comment(lines[ln - 1])
            if LISTEN_SSL_RE.match(stripped):
                tls_blocks.append((start, end))
                break

    # http {} block: treat any ssl_protocols outside a server block as
    # potentially applying to a TLS server iff at least one TLS server
    # block exists in the file.
    file_has_tls_server = bool(tls_blocks)

    for ln_idx, raw in enumerate(lines, start=1):
        m = SSL_PROTOCOLS_RE.match(raw)
        if not m:
            continue
        if SUPPRESS_RE.search(raw):
            continue
        protos = m.group(1).split()
        bad = [p for p in protos if p in LEGACY_PROTOCOLS]
        if not bad:
            continue
        # Is this directive inside a TLS server block, or in an http
        # block of a file that has at least one TLS server?
        inside_tls = any(s <= ln_idx <= e for s, e in tls_blocks)
        if not inside_tls and not file_has_tls_server:
            continue
        findings.append((
            ln_idx,
            (
                f"ssl_protocols enables deprecated {','.join(bad)} — "
                "remove and keep only TLSv1.2 / TLSv1.3"
            ),
        ))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("nginx.conf", "*.conf"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

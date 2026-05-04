#!/usr/bin/env python3
"""Detect Tinyproxy configurations that turn the daemon into an open
forward proxy reachable from the internet — the exact shape that LLM
"how do I run a quick HTTP proxy" snippets emit.

Tinyproxy's default ``tinyproxy.conf`` ships with one or more
``Allow 127.0.0.1`` lines and a public ``Listen``/``Bind`` either
absent or set to ``0.0.0.0``. When users (or LLM-generated
quickstarts) add ``Allow 0.0.0.0/0`` (or ``Allow 0/0``) they remove
the only thing keeping random hosts on the internet from using the
proxy as an anonymizing relay — a well-documented vector for credit-
card carding, scraping abuse, and reflection of egress through a
victim's IP.

Rules: a finding is emitted when ALL of:

1. The config is bound to a public address. ``Listen`` is missing,
   or set to ``0.0.0.0`` / ``::`` / ``[::]`` / a routable IP. (A
   ``Listen 127.0.0.1`` / ``Listen ::1`` line is treated as
   loopback-only and the file is not flagged.)
2. At least one ``Allow`` directive matches ``0.0.0.0/0``,
   ``0.0.0.0`` (no mask), ``0/0``, ``::/0``, or ``::``.
3. ``BasicAuth`` is NOT configured. (BasicAuth still leaves the
   proxy open in the network sense, but at least requires a
   credential, so we treat it as a separate concern out of scope.)

A line containing the marker ``# tinyproxy-public-allowed``
suppresses the finding for the whole file.

Stdlib-only. Exit code is the count of files with at least one
finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*tinyproxy-public-allowed")

LISTEN_RE = re.compile(r"^\s*Listen\s+(\S+)", re.IGNORECASE)
BIND_RE = re.compile(r"^\s*Bind\s+(\S+)", re.IGNORECASE)
ALLOW_RE = re.compile(r"^\s*Allow\s+(\S+)", re.IGNORECASE)
BASIC_AUTH_RE = re.compile(r"^\s*BasicAuth\s+\S+\s+\S+", re.IGNORECASE)

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]"}
WILDCARD_ALLOWS = {
    "0.0.0.0/0",
    "0.0.0.0",
    "0/0",
    "::/0",
    "::",
}


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    listen_value: str = ""  # empty == not set => default all-interfaces
    listen_line: int = 0
    has_basic_auth = False
    open_allows: List[Tuple[int, str]] = []

    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.split("#", 1)[0]
        if not stripped.strip():
            continue
        m = LISTEN_RE.match(stripped)
        if m:
            listen_value = m.group(1).strip()
            listen_line = i
            continue
        m = BIND_RE.match(stripped)
        if m and not listen_value:
            # Bind controls the *outbound* source IP, not the listen
            # interface, but treat a non-loopback Bind as evidence the
            # operator is intentionally networking. We still rely on
            # Listen for the public-binding decision.
            pass
        if BASIC_AUTH_RE.match(stripped):
            has_basic_auth = True
            continue
        m = ALLOW_RE.match(stripped)
        if m:
            target = m.group(1).strip().rstrip(",")
            if target in WILDCARD_ALLOWS:
                open_allows.append((i, target))
            continue

    # Decide listen scope.
    if listen_value:
        host = listen_value
        if host.startswith("["):
            end = host.find("]")
            if end != -1:
                host = host[1:end]
        if host in LOOPBACK:
            return findings  # loopback-only deployment
        is_public = host in WILDCARD_HOSTS or _looks_like_routable(host)
    else:
        # No Listen directive => Tinyproxy listens on all interfaces.
        is_public = True

    if not is_public:
        return findings
    if has_basic_auth:
        return findings
    if not open_allows:
        return findings

    for line, target in open_allows:
        findings.append((
            line,
            (
                f"Tinyproxy 'Allow {target}' on a public listener "
                f"(Listen={listen_value or '<unset, default 0.0.0.0>'}) "
                "with no BasicAuth — open forward proxy"
            ),
        ))
    return findings


def _looks_like_routable(host: str) -> bool:
    # Anything that is not a known loopback and not a domain-only token
    # we treat as a routable bind. Domains with letters are also
    # treated as routable (a public hostname).
    if host in LOOPBACK:
        return False
    if host in WILDCARD_HOSTS:
        return False
    return True


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("tinyproxy.conf", "*.tinyproxy.conf", "*.conf"):
                targets.extend(sorted(path.rglob(pat)))
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

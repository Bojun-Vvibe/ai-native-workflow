#!/usr/bin/env python3
"""Detect Redis ``redis.conf`` files that ship without authentication
and/or with protected-mode disabled while bound to a non-loopback
interface.

A Redis instance with no ``requirepass`` (and no ACL ``user`` entries
with passwords), ``protected-mode no``, and ``bind 0.0.0.0`` (or any
non-loopback bind, or no ``bind`` at all on Redis < 6.2) is a
well-known internet-wide compromise vector: attackers write SSH keys
into ``~/.ssh/authorized_keys`` via ``CONFIG SET dir`` + ``SAVE``, load
arbitrary modules via ``MODULE LOAD``, or simply exfiltrate the
keyspace.

LLM-generated ``redis.conf`` files routinely paste in::

    bind 0.0.0.0
    protected-mode no
    # requirepass commented out

This detector flags those config shapes.

What's checked (per file):
  - ``protected-mode no`` is present.
  - There is no active ``requirepass <secret>`` directive (commented
    out, empty value, or literal ``foobared`` placeholder all count as
    missing) AND no ACL ``user`` line that requires a password.
  - ``bind`` exposes a non-loopback interface (or ``bind`` is absent,
    which prior to 6.2 meant "all interfaces").

The detector reports per-line findings for the offending directives
plus a synthesized summary line if all three conditions coincide.

CWE refs:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-284: Improper Access Control
  - CWE-668: Exposure of Resource to Wrong Sphere

False-positive surface:
  - Local-dev compose files behind a private docker network. Suppress
    per file with a top comment ``# redis-no-auth-allowed`` on any
    line.
  - ``bind 127.0.0.1 ::1`` only is treated as safe.
  - ``requirepass`` provided via env var indirection (``${REDIS_PASS}``
    style) is treated as set.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*redis-no-auth-allowed")

BIND_RE = re.compile(r"^\s*bind\s+(.+?)\s*(?:#.*)?$", re.IGNORECASE)
PROTECTED_MODE_NO_RE = re.compile(r"^\s*protected-mode\s+no\b", re.IGNORECASE)
REQUIREPASS_RE = re.compile(r"^\s*requirepass\s+(\S+)", re.IGNORECASE)
USER_ACL_RE = re.compile(r"^\s*user\s+\S+.*", re.IGNORECASE)
PORT_RE = re.compile(r"^\s*port\s+0\b", re.IGNORECASE)  # port 0 disables TCP

# Loopback-only set.
LOOPBACK = {"127.0.0.1", "::1", "localhost"}

# Placeholder/empty requirepass values that should not count as set.
WEAK_PASSES = {"", "''", '""', "foobared", "changeme", "password"}


def _bind_is_loopback_only(value: str) -> bool:
    addrs = re.split(r"[\s,]+", value.strip())
    addrs = [a.strip("'\"") for a in addrs if a]
    if not addrs:
        return False
    return all(a in LOOPBACK for a in addrs)


def _user_has_password(line: str) -> bool:
    # Redis ACL: `user alice on >pa55 ~* +@all`
    # Password tokens start with `>` (literal) or `#` (sha256). `nopass`
    # explicitly disables auth.
    tokens = line.split()
    has_pw = any(t.startswith(">") or t.startswith("#") for t in tokens[1:])
    nopass = "nopass" in tokens
    on = "on" in tokens
    return on and has_pw and not nopass


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    has_bind = False
    bind_loopback_only = False
    bind_line = 0
    bind_value = ""

    protected_mode_no_line = 0
    requirepass_line = 0
    requirepass_set = False
    acl_user_with_pw = False

    tcp_disabled = False

    for i, raw in enumerate(source.splitlines(), start=1):
        # Strip inline comments for matching, but keep raw for context.
        line_no_comment = raw.split("#", 1)[0]
        if not line_no_comment.strip():
            continue

        if PORT_RE.search(line_no_comment):
            tcp_disabled = True

        m = BIND_RE.match(line_no_comment)
        if m:
            has_bind = True
            bind_line = i
            bind_value = m.group(1).strip()
            bind_loopback_only = _bind_is_loopback_only(bind_value)
            continue

        if PROTECTED_MODE_NO_RE.search(line_no_comment):
            protected_mode_no_line = i
            continue

        m = REQUIREPASS_RE.match(line_no_comment)
        if m:
            val = m.group(1).strip().strip("'\"")
            if val and val.lower() not in WEAK_PASSES:
                requirepass_set = True
                requirepass_line = i
            continue

        if USER_ACL_RE.match(line_no_comment):
            if _user_has_password(line_no_comment):
                acl_user_with_pw = True
            continue

    # If TCP is disabled, exposure surface is gone.
    if tcp_disabled:
        return findings

    auth_present = requirepass_set or acl_user_with_pw

    # bind absent => historically all-interfaces; treat as exposed.
    bind_exposed = (not has_bind) or (has_bind and not bind_loopback_only)

    if protected_mode_no_line and not auth_present:
        findings.append((
            protected_mode_no_line,
            "protected-mode no without requirepass / ACL password disables auth",
        ))

    if bind_exposed and not auth_present:
        if has_bind:
            findings.append((
                bind_line,
                f"bind exposes non-loopback ({bind_value}) without requirepass / ACL password",
            ))
        else:
            findings.append((
                1,
                "no bind directive (defaults to all interfaces) without requirepass / ACL password",
            ))

    if protected_mode_no_line and bind_exposed and not auth_present:
        findings.append((
            protected_mode_no_line,
            "trifecta: bind=non-loopback + protected-mode no + no auth — internet-exposed Redis CVE pattern",
        ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("redis.conf", "*.redis.conf", "redis-*.conf"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    for f in targets:
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

#!/usr/bin/env python3
"""Detect PostgreSQL ``pg_hba.conf`` files that grant access via the
``trust`` authentication method on a non-loopback line.

``trust`` means *no password, no certificate, no Kerberos — anyone who
can reach the TCP port wins*. It is appropriate only for Unix-socket
``local`` lines on a single-tenant developer machine. LLMs asked to
"give me a pg_hba.conf that lets my app connect" routinely paste in
shapes like::

    host  all  all  0.0.0.0/0   trust
    host  all  all  ::/0        trust
    host  all  all  10.0.0.0/8  trust

…all of which expose the database to anyone who can route packets to
it.

What's flagged
--------------
Per non-comment, non-blank line, with at least 4 whitespace-separated
fields, where:

* The connection type field is ``host``, ``hostssl``, ``hostnossl``,
  ``hostgssenc``, or ``hostnogssenc`` (i.e. TCP, not Unix socket); AND
* The auth method (last token, ignoring trailing ``key=value`` options)
  is ``trust``; AND
* The address field is *not* loopback-only (``127.0.0.1/32``,
  ``::1/128``, or the literal ``localhost``/``samehost``).

Also flagged (regardless of address):

* ``host all all <addr> trust`` with ``<addr>`` ending in ``/0`` —
  always a public-internet pattern, even if someone marks it
  ``samenet``.

What's NOT flagged
------------------
* ``local all all trust`` — Unix-socket local; flagged as a separate
  *info* finding only when ``# pg-trust-strict`` appears in the file.
* ``host all all 127.0.0.1/32 trust`` and ``::1/128 trust`` — loopback.
* ``host all all 0.0.0.0/0 scram-sha-256`` — real auth method.
* ``host all all 10.0.0.0/8 cert`` — certificate auth.
* Lines suppressed with a trailing ``# pg-trust-ok`` comment.
* Files containing ``# pg-trust-ok-file`` anywhere.

CWE refs
--------
* CWE-287: Improper Authentication
* CWE-306: Missing Authentication for Critical Function
* CWE-668: Exposure of Resource to Wrong Sphere

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*pg-trust-ok\b")
SUPPRESS_FILE = re.compile(r"#\s*pg-trust-ok-file\b")
STRICT_LOCAL = re.compile(r"#\s*pg-trust-strict\b")

HOST_TYPES = {
    "host", "hostssl", "hostnossl", "hostgssenc", "hostnogssenc",
}
LOOPBACK_ADDRS = {
    "127.0.0.1/32",
    "127.0.0.1",
    "::1/128",
    "::1",
    "localhost",
    "samehost",
}


def _is_loopback(addr: str) -> bool:
    addr = addr.strip()
    if addr in LOOPBACK_ADDRS:
        return True
    # 127.0.0.0/8 is technically loopback per RFC, but pg_hba doesn't
    # treat it as the canonical loopback line; only /32 of 127.0.0.1
    # and ::1/128 are. Be conservative and flag anything else.
    return False


def _strip_inline_comment(line: str) -> str:
    return line.split("#", 1)[0]


def _tokens(line: str) -> List[str]:
    return [t for t in re.split(r"[\s,]+", line.strip()) if t]


def _auth_method(tokens: List[str]) -> str:
    """Return the auth method token. pg_hba allows trailing
    ``key=value`` option tokens after the method, so we walk from the
    right and skip anything containing ``=``."""
    for tok in reversed(tokens):
        if "=" in tok:
            continue
        return tok.lower()
    return ""


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings
    strict_local = bool(STRICT_LOCAL.search(source))

    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            continue
        line = _strip_inline_comment(raw).strip()
        if not line:
            continue
        toks = _tokens(line)
        if len(toks) < 4:
            continue

        conn_type = toks[0].lower()
        method = _auth_method(toks)

        if method != "trust":
            continue

        if conn_type == "local":
            if strict_local:
                findings.append((
                    i,
                    "local trust auth flagged under pg-trust-strict mode",
                ))
            continue

        if conn_type not in HOST_TYPES:
            # Unknown connection type — be conservative and skip.
            continue

        # For host* lines, structure is:
        #   <type> <database> <user> <address> [<mask>] <method> [opts]
        # The address is field index 3. If a separate netmask follows
        # (no slash in the address), it's at index 4.
        addr = toks[3]
        if "/" not in addr and len(toks) >= 6:
            # IPv4 with explicit netmask in next column.
            addr_full = f"{addr}/{toks[4]}"
        else:
            addr_full = addr

        if _is_loopback(addr) or _is_loopback(addr_full):
            continue

        if addr_full.endswith("/0"):
            findings.append((
                i,
                f"{conn_type} trust auth on public-internet CIDR {addr_full}",
            ))
            continue

        findings.append((
            i,
            f"{conn_type} trust auth on non-loopback address {addr_full}",
        ))

    return findings


def _iter_hba_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    for pattern in ("pg_hba.conf", "*.pg_hba.conf", "pg_hba-*.conf"):
        for sub in sorted(path.rglob(pattern)):
            if sub.is_file() and sub not in seen:
                seen.add(sub)
                yield sub


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for root in paths:
        for f in _iter_hba_files(root):
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

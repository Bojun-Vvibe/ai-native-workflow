#!/usr/bin/env python3
"""Detect Apache Solr environment / launcher configurations that
enable the JMX RMI server without authentication.

Solr ships with a built-in switch (``ENABLE_REMOTE_JMX_OPTS=true``)
in ``solr.in.sh`` / ``solr.in.cmd`` that opens an RMI registry on
``RMI_PORT`` (default 18983). When set, the standard launcher
emits the JVM flags::

    -Dcom.sun.management.jmxremote
    -Dcom.sun.management.jmxremote.port=<RMI_PORT>
    -Dcom.sun.management.jmxremote.rmi.port=<RMI_PORT>
    -Dcom.sun.management.jmxremote.local.only=false
    -Dcom.sun.management.jmxremote.authenticate=false
    -Dcom.sun.management.jmxremote.ssl=false

Without ``jmxremote.authenticate=true`` (or
``jmxremote.password.file=…`` configured), anything that can reach
the RMI port can:

  - Read every JMX MBean (heap stats, system properties — including
    ones containing secrets passed via ``-D``, request metrics,
    Solr-internal state).
  - Invoke any registered MBean operation. Historically this has
    been chained into RCE via the ``MLet`` loader, ``Diagnostic
    Command``, or arbitrary ``MBeanServer`` operations to load
    remote bytecode (CVE-2016-3427 family, JNDI-injection variants).
  - Dump arbitrary serialized objects from JMX, expanding any
    deserialization-gadget surface the JVM has.

This is the same class of finding that tracks as CWE-306 (Missing
Authentication for Critical Function) and OWASP A07:2021
Identification and Authentication Failures. LLM-generated Solr
configs frequently emit shapes like::

    ENABLE_REMOTE_JMX_OPTS="true"
    RMI_PORT="18983"

…with no companion ``jmxremote.password.file`` or
``jmxremote.authenticate=true`` override anywhere, and no firewall
note.

What's checked, per file:

  - ``ENABLE_REMOTE_JMX_OPTS`` is set to a truthy value (``true``,
    ``yes``, ``1``, ``on``, case-insensitive), in shell-style
    (``KEY=value`` / ``export KEY=value``) or in Windows cmd-style
    (``set KEY=value``).
  - The same file does NOT also set
    ``-Dcom.sun.management.jmxremote.authenticate=true`` (anywhere)
    AND does NOT set
    ``-Dcom.sun.management.jmxremote.password.file=...`` to a
    non-empty value AND does NOT set
    ``com.sun.management.jmxremote.access.file=...``.

Accepted (not flagged):

  - ``ENABLE_REMOTE_JMX_OPTS=false`` (or unset / commented out).
  - ``ENABLE_REMOTE_JMX_OPTS=true`` together with an explicit
    ``jmxremote.authenticate=true`` or ``jmxremote.password.file=…``
    or ``jmxremote.access.file=…`` override in the same file.
  - Files containing the comment ``# solr-jmx-no-auth-allowed``
    (intentional internal-only fixture, e.g. a single-node
    container behind a private subnet).
  - Files that don't mention ``ENABLE_REMOTE_JMX_OPTS`` at all.

Usage::

    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at
255). Stdout: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*solr-jmx-no-auth-allowed", re.IGNORECASE)

TRUTHY = {"true", "yes", "1", "on"}

# Match shell- or cmd-style assignment of ENABLE_REMOTE_JMX_OPTS.
# Allowed shapes:
#   ENABLE_REMOTE_JMX_OPTS=true
#   ENABLE_REMOTE_JMX_OPTS="true"
#   export ENABLE_REMOTE_JMX_OPTS=true
#   set ENABLE_REMOTE_JMX_OPTS=true
ENABLE_RE = re.compile(
    r"""^\s*
        (?:export\s+|set\s+)?
        ENABLE_REMOTE_JMX_OPTS
        \s*=\s*
        (?P<q>['"]?)
        (?P<val>[A-Za-z0-9]+)
        (?P=q)
        \s*(?:\#.*)?$
    """,
    re.IGNORECASE | re.VERBOSE,
)

AUTH_TRUE_RE = re.compile(
    r"-D\s*com\.sun\.management\.jmxremote\.authenticate\s*=\s*true",
    re.IGNORECASE,
)
PASSWORD_FILE_RE = re.compile(
    r"-D\s*com\.sun\.management\.jmxremote\.password\.file\s*=\s*"
    r"(?P<val>\S+)",
    re.IGNORECASE,
)
ACCESS_FILE_RE = re.compile(
    r"-D\s*com\.sun\.management\.jmxremote\.access\.file\s*=\s*"
    r"(?P<val>\S+)",
    re.IGNORECASE,
)


def _line_is_uncommented(raw: str) -> bool:
    s = raw.lstrip()
    if not s:
        return False
    if s.startswith("#") or s.startswith("//") or s.startswith("REM "):
        return False
    return True


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    enabled_lines: List[int] = []
    for idx, raw in enumerate(source.splitlines(), start=1):
        if not _line_is_uncommented(raw):
            continue
        m = ENABLE_RE.match(raw)
        if not m:
            continue
        if m.group("val").lower() in TRUTHY:
            enabled_lines.append(idx)

    if not enabled_lines:
        return findings

    # Companion-flag check across the whole file (uncommented lines).
    has_auth_true = False
    has_password_file = False
    has_access_file = False
    for raw in source.splitlines():
        if not _line_is_uncommented(raw):
            continue
        if AUTH_TRUE_RE.search(raw):
            has_auth_true = True
        m = PASSWORD_FILE_RE.search(raw)
        if m and m.group("val") and m.group("val") not in {'""', "''"}:
            has_password_file = True
        m2 = ACCESS_FILE_RE.search(raw)
        if m2 and m2.group("val") and m2.group("val") not in {'""', "''"}:
            has_access_file = True

    if has_auth_true or has_password_file or has_access_file:
        return findings

    for ln in enabled_lines:
        findings.append(
            (
                ln,
                "Solr ENABLE_REMOTE_JMX_OPTS=true with no "
                "jmxremote.authenticate=true / password.file / "
                "access.file companion (CWE-306)",
            )
        )
    return findings


def _is_solr_env(path: Path) -> bool:
    name = path.name.lower()
    if name in {"solr.in.sh", "solr.in.cmd", "solr.in.bash"}:
        return True
    if name.endswith((".sh", ".bash", ".cmd", ".bat", ".env", ".conf")):
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_solr_env(f):
                    targets.append(f)
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

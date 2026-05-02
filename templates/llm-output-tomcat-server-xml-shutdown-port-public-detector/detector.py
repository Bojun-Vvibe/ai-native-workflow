#!/usr/bin/env python3
"""Detect Apache Tomcat ``server.xml`` files where the top-level
``<Server>`` element exposes its shutdown port unsafely.

Tomcat's ``<Server port="N" shutdown="WORD">`` element opens a TCP
listener on ``port`` (default ``8005``) that, when it receives the
plaintext ``shutdown`` string, gracefully stops the JVM. Two common
LLM-generated mistakes turn this into a remote DoS / takedown
primitive:

1. ``shutdown="SHUTDOWN"`` left at the documented default. Anyone
   who can reach the port can ``echo SHUTDOWN | nc host 8005`` and
   stop the server. This is fine ONLY if the port is bound to
   loopback (``address="127.0.0.1"`` / ``::1``) AND the host is
   trusted.

2. The ``<Server>`` element omits ``address=`` (Tomcat then binds
   to the wildcard address on multi-homed hosts depending on
   version) OR explicitly sets ``address="0.0.0.0"`` /
   ``address="::"``. Combined with the default shutdown command
   this is remotely exploitable.

What's checked (per file):
  - The first ``<Server ...>`` element's attributes are parsed.
  - ``port="-1"`` disables the listener entirely → safe.
  - ``shutdown="SHUTDOWN"`` (case-sensitive — Tomcat compares
    literally) is treated as the default magic word.
  - ``address`` attribute, if present, must be a loopback literal
    (``127.0.0.1``, ``localhost``, ``::1``) to be considered safe.
  - Missing ``address`` attribute is treated as "binds non-loopback"
    because that is the historical Tomcat default on the shutdown
    socket.

CWE refs:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-749: Exposed Dangerous Method or Function
  - CWE-16:  Configuration

False-positive surface:
  - Embedded Tomcat behind a host firewall that drops 8005 — still
    flagged; suppress per file with a comment
    ``<!-- tomcat-shutdown-port-reviewed -->`` anywhere in the file.
  - Non-default ``shutdown`` magic word with loopback bind is treated
    as safe.

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

SUPPRESS = re.compile(r"tomcat-shutdown-port-reviewed")

# Match the opening <Server ...> tag (allow attributes spanning
# multiple lines). We only care about the first one in the file.
SERVER_TAG_RE = re.compile(r"<Server\b([^>]*)>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(
    r"""(\w[\w:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
    re.DOTALL,
)

LOOPBACK_LITERALS = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}


def _parse_attrs(blob: str) -> dict:
    out = {}
    for m in ATTR_RE.finditer(blob):
        out[m.group(1).lower()] = m.group(2) if m.group(2) is not None else m.group(3)
    return out


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    m = SERVER_TAG_RE.search(source)
    if not m:
        return findings

    attrs = _parse_attrs(m.group(1))
    line = _line_of(source, m.start())

    port = attrs.get("port", "8005").strip()
    if port == "-1":
        return findings  # listener disabled

    shutdown = attrs.get("shutdown", "SHUTDOWN")
    address = attrs.get("address", "").strip()

    is_default_word = shutdown == "SHUTDOWN"
    is_loopback = address in LOOPBACK_LITERALS

    if is_default_word and not is_loopback:
        if not address:
            findings.append((
                line,
                f'<Server port="{port}" shutdown="SHUTDOWN"> with no '
                f"address= attribute — default shutdown command "
                f"reachable on non-loopback bind",
            ))
        else:
            findings.append((
                line,
                f'<Server port="{port}" shutdown="SHUTDOWN" '
                f'address="{address}"> — default shutdown command '
                f"reachable on non-loopback address",
            ))
    elif is_default_word and is_loopback:
        # default word but loopback-bound: warn lightly only if port
        # is explicitly the documented default — many guides copy this
        # pair without thinking.
        if port == "8005":
            # loopback + default word + default port: not a finding
            return findings
    elif (not is_default_word) and (not is_loopback) and address:
        findings.append((
            line,
            f'<Server port="{port}" shutdown="{shutdown}" '
            f'address="{address}"> — non-default magic word but bound '
            f"to non-loopback; review whether the magic word is "
            f"actually secret",
        ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("server.xml", "*server.xml"):
                targets.extend(sorted(path.rglob(pat)))
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

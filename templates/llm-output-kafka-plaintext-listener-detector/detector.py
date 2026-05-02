#!/usr/bin/env python3
"""Detect Kafka broker configs that expose a ``PLAINTEXT://`` listener
on a non-loopback interface, or that explicitly map a non-loopback
listener to the ``PLAINTEXT`` security protocol via
``listener.security.protocol.map``.

Background
----------
Kafka brokers accept connections on listeners declared by the
``listeners=`` and ``advertised.listeners=`` properties (typically in
``server.properties``). Each listener has a name, a host, and a port,
e.g.::

    listeners=PLAINTEXT://0.0.0.0:9092,SSL://0.0.0.0:9093

The default listener name ``PLAINTEXT`` maps, by default, to the
``PLAINTEXT`` security protocol — *no TLS, no SASL, no auth, no
encryption*. Any client that can route packets to the port can produce,
consume, and (with ACLs default-allow) administer.

LLMs asked to "give me a quick Kafka config" almost always paste
``listeners=PLAINTEXT://0.0.0.0:9092``, which is fine for a single-host
docker-compose dev box but catastrophic on any shared network.

What's flagged
--------------
A line in a Kafka properties file where, after stripping comments:

* The key is ``listeners`` or ``advertised.listeners``; AND
* At least one comma-separated entry has scheme ``PLAINTEXT://`` (or a
  custom listener name that is mapped to ``PLAINTEXT`` via
  ``listener.security.protocol.map`` in the same file); AND
* The host portion is not loopback (``127.0.0.1``, ``::1``,
  ``localhost``) and not empty/missing.

Hosts that are flagged:

* ``0.0.0.0`` and ``::`` (all interfaces) — loudest finding.
* Any concrete non-loopback IP or hostname.
* Empty host (``PLAINTEXT://:9092``) — Kafka binds all interfaces.

What's NOT flagged
------------------
* ``PLAINTEXT://127.0.0.1:9092`` and ``PLAINTEXT://localhost:9092``.
* Listeners with scheme ``SSL://``, ``SASL_SSL://``, ``SASL_PLAINTEXT://``
  on any host (SASL_PLAINTEXT has its own template).
* Lines with trailing ``# kafka-plaintext-ok`` comment.
* Files containing ``# kafka-plaintext-ok-file`` anywhere.
* Custom listener names that are explicitly remapped to
  ``SSL`` / ``SASL_SSL`` in ``listener.security.protocol.map``.

CWE refs
--------
* CWE-319: Cleartext Transmission of Sensitive Information
* CWE-306: Missing Authentication for Critical Function
* CWE-200: Exposure of Sensitive Information

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
from typing import Dict, Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*kafka-plaintext-ok\b")
SUPPRESS_FILE = re.compile(r"#\s*kafka-plaintext-ok-file\b")

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "[::1]", "localhost"}

LISTENER_KEYS = {"listeners", "advertised.listeners"}
PROTOCOL_MAP_KEY = "listener.security.protocol.map"

LISTENER_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9_]+)://(?P<host>\[[^\]]*\]|[^:/,]*):(?P<port>\d+)\s*$"
)


def _strip_inline_comment(line: str) -> str:
    return line.split("#", 1)[0]


def _parse_kv(line: str) -> Tuple[str, str] | None:
    body = _strip_inline_comment(line).strip()
    if not body:
        return None
    if "=" not in body:
        return None
    key, _, value = body.partition("=")
    return key.strip(), value.strip()


def _parse_protocol_map(value: str) -> Dict[str, str]:
    """``LNAME1:PROTO1,LNAME2:PROTO2`` -> {LNAME: PROTO}, both upper."""
    out: Dict[str, str] = {}
    for entry in value.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        ln, _, proto = entry.partition(":")
        out[ln.strip().upper()] = proto.strip().upper()
    return out


def _is_loopback(host: str) -> bool:
    return host.strip().lower() in LOOPBACK_HOSTS


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    # First pass: collect protocol map (last assignment wins).
    proto_map: Dict[str, str] = {}
    for raw in source.splitlines():
        kv = _parse_kv(raw)
        if not kv:
            continue
        if kv[0] == PROTOCOL_MAP_KEY:
            proto_map = _parse_protocol_map(kv[1])

    # Second pass: walk listener lines.
    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            continue
        kv = _parse_kv(raw)
        if not kv:
            continue
        key, value = kv
        if key not in LISTENER_KEYS:
            continue

        for entry in value.split(","):
            entry = entry.strip()
            if not entry:
                continue
            m = LISTENER_RE.match(entry)
            if not m:
                continue
            name = m.group("name").upper()
            host = m.group("host")
            # Resolve the security protocol for this listener name.
            proto = proto_map.get(name, name)
            if proto != "PLAINTEXT":
                continue

            if _is_loopback(host):
                continue

            if host == "" or host == "0.0.0.0" or host in ("::", "[::]"):
                reason = (
                    f"{key}={entry}: PLAINTEXT listener bound to all "
                    f"interfaces ({host or '<empty>'})"
                )
            else:
                reason = (
                    f"{key}={entry}: PLAINTEXT listener bound to "
                    f"non-loopback host {host}"
                )
            findings.append((i, reason))

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    for pattern in ("server.properties", "*.server.properties", "kafka-*.properties"):
        for sub in sorted(path.rglob(pattern)):
            if sub.is_file() and sub not in seen:
                seen.add(sub)
                yield sub


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for root in paths:
        for f in _iter_files(root):
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

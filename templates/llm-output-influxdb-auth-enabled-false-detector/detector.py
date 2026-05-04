#!/usr/bin/env python3
"""Detect InfluxDB 1.x configurations that disable HTTP authentication
on a publicly reachable instance — the exact shape that LLM "give me
a quick InfluxDB I can hit from Grafana" snippets emit.

InfluxDB 1.x ships ``influxdb.conf`` with ``[http]`` section
``auth-enabled = false`` as the default. The instance is also bound
to ``:8086`` (all interfaces) by default. When users follow an LLM
snippet that says "to make it work with Grafana / curl, set auth-
enabled to false", they leave a database server listening on every
interface with no authentication at all — read, write, and admin
(``CREATE USER``, ``DROP DATABASE``) all unauthenticated.

Rules: a finding is emitted when ALL of:

1. The ``[http]`` section sets ``auth-enabled = false`` (or the value
   is left at the default ``false`` while ``enabled = true``). We only
   flag explicit ``false``; missing ``auth-enabled`` is not flagged
   because we cannot tell the operator's intent without the binary
   default. Variants accepted: ``auth-enabled = false``,
   ``auth-enabled=false``, with optional surrounding whitespace.
2. The ``[http]`` section is enabled (``enabled = true``, or the line
   is absent — the binary defaults to ``enabled = true``).
3. The ``bind-address`` is empty, missing, ``":8086"``, ``"0.0.0.0:..."``,
   ``"[::]:..."``, or any non-loopback host. ``"127.0.0.1:8086"`` /
   ``"[::1]:8086"`` / ``"localhost:..."`` are treated as loopback-only
   and the file is NOT flagged.

A line containing the marker ``# influxdb-auth-disabled-allowed``
suppresses the finding for the whole file (use this for intentional
read-only dev sandboxes behind a firewall).

Stdlib-only. Exit code is the count of files with at least one
finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*influxdb-auth-disabled-allowed")

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*(.+?)\s*(?:#.*)?$")

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "[::1]"}


def _strip_quotes(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'"):
        return v[1:-1]
    return v


def _bind_is_loopback(bind: str) -> bool:
    """Return True iff bind-address binds only loopback."""
    b = _strip_quotes(bind).strip()
    if not b:
        return False  # empty == listen on all interfaces
    # Forms: "host:port", ":port", "[::1]:port", "host"
    host = b
    if b.startswith("["):
        end = b.find("]")
        if end != -1:
            host = b[: end + 1]
    elif ":" in b:
        host = b.rsplit(":", 1)[0]
    if not host:
        return False  # ":8086"
    return host in LOOPBACK_HOSTS


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    section: Optional[str] = None
    http_auth_disabled_line: int = 0
    http_auth_value_seen: Optional[bool] = None
    http_enabled: Optional[bool] = None  # tri-state
    http_bind: Optional[str] = None
    http_bind_line: int = 0

    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#", 1)[0] if "#" in raw and not raw.lstrip().startswith("#") else raw
        # We don't strip '#' if the whole line is a comment — handled by KV_RE failing
        sm = SECTION_RE.match(raw.split("#", 1)[0])
        if sm:
            section = sm.group(1).strip().lower()
            continue
        if section != "http":
            continue
        if raw.lstrip().startswith("#"):
            continue
        km = KV_RE.match(raw)
        if not km:
            continue
        key = km.group(1).strip().lower()
        val = km.group(2).strip()
        # Strip trailing inline comment if KV_RE didn't catch (it did, but be safe)
        if val.lower() in ("true", "false"):
            bool_val = val.lower() == "true"
        else:
            bool_val = None  # non-bool

        if key == "auth-enabled":
            if bool_val is False:
                http_auth_disabled_line = i
                http_auth_value_seen = False
            elif bool_val is True:
                http_auth_value_seen = True
        elif key == "enabled":
            if bool_val is not None:
                http_enabled = bool_val
        elif key == "bind-address":
            http_bind = val
            http_bind_line = i

    # Decision
    if http_auth_value_seen is not False:
        return findings
    if http_enabled is False:
        return findings  # http listener off entirely
    # http_enabled is True or None (default true)

    if http_bind is not None and _bind_is_loopback(http_bind):
        return findings

    bind_disp = http_bind if http_bind is not None else "<unset, default :8086>"
    findings.append((
        http_auth_disabled_line,
        (
            "InfluxDB [http] auth-enabled = false on a non-loopback "
            f"bind-address ({bind_disp}) — unauthenticated read/write/admin"
        ),
    ))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("influxdb.conf", "*.influxdb.conf", "*.conf", "*.toml"):
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

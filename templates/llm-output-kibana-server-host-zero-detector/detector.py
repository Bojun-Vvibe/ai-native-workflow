#!/usr/bin/env python3
"""Detect Kibana ``kibana.yml`` files that bind ``server.host`` to all
network interfaces (``0.0.0.0`` / ``0`` / ``"::"`` / ``"*"``).

Kibana's default ``server.host`` is ``localhost``. LLM-generated
configs routinely "fix the can't-connect-from-outside" problem by
changing it to ``0.0.0.0``, accidentally publishing the dashboard — and
any indices it can read — to the wider network. When paired with
``xpack.security.enabled: false`` (or no security plugin), anyone who
can reach the host has full read of every index Kibana sees.

What's checked (per file):
  - ``server.host`` set to ``0.0.0.0`` / ``0`` / ``"0"`` / ``"::"`` /
    ``"*"`` (with or without quotes).
  - ``xpack.security.enabled: false`` is captured to escalate the
    bind-all finding to "bind-all + no auth".

CWE refs:
  - CWE-668: Exposure of Resource to Wrong Sphere
  - CWE-306: Missing Authentication for Critical Function
  - CWE-200: Exposure of Sensitive Information to an Unauthorized
    Actor

False-positive surface:
  - Containerized Kibana that is genuinely fronted by an
    authenticating reverse proxy on a private network. Suppress per
    file with a comment ``# kibana-bind-all-allowed`` anywhere in the
    file.
  - ``server.host: "127.0.0.1"`` / ``localhost`` / a specific
    non-wildcard IP is treated as safe.

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

SUPPRESS = re.compile(r"#\s*kibana-bind-all-allowed")

SERVER_HOST_RE = re.compile(
    r"""^\s*server\.host\s*:\s*(?P<val>['"]?[^#\n]+?['"]?)\s*(?:\#.*)?$""",
    re.IGNORECASE,
)

SECURITY_ENABLED_FALSE_RE = re.compile(
    r"^\s*xpack\.security\.enabled\s*:\s*false\b", re.IGNORECASE
)
SECURITY_ENABLED_TRUE_RE = re.compile(
    r"^\s*xpack\.security\.enabled\s*:\s*true\b", re.IGNORECASE
)

WILDCARD_HOSTS = {"0.0.0.0", "0", "::", "*"}


def _normalize(value: str) -> str:
    return value.strip().strip("'\"").strip()


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    bind_line = 0
    bind_value = ""
    bind_is_wildcard = False

    security_false_line = 0
    security_true = False

    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        m = SERVER_HOST_RE.match(raw)
        if m:
            val = _normalize(m.group("val"))
            if val in WILDCARD_HOSTS:
                bind_line = i
                bind_value = val
                bind_is_wildcard = True
            continue

        if SECURITY_ENABLED_FALSE_RE.search(raw):
            security_false_line = i
            continue
        if SECURITY_ENABLED_TRUE_RE.search(raw):
            security_true = True
            continue

    if bind_is_wildcard:
        if security_false_line:
            findings.append((
                bind_line,
                f"server.host={bind_value!r} (all interfaces) AND xpack.security.enabled: false on line "
                f"{security_false_line} — Kibana exposed without auth",
            ))
        elif not security_true:
            findings.append((
                bind_line,
                f"server.host={bind_value!r} binds Kibana to all interfaces with no explicit "
                f"xpack.security.enabled: true — likely public exposure without auth",
            ))
        # If security_true is set, we stay silent (info-only handled
        # via README; exit code unaffected).

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("kibana.yml", "kibana.yaml", "*.kibana.yml"):
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

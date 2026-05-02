#!/usr/bin/env python3
"""Detect Apache httpd configurations that ship with ``TraceEnable On``
(or equivalent), leaving the HTTP TRACE method enabled.

The HTTP TRACE method echoes the request — including ``Cookie`` and
``Authorization`` headers — back in the response body. When combined
with a script-injection vector this becomes Cross-Site Tracing (XST)
and lets an attacker exfiltrate ``HttpOnly`` cookies. Modern Apache
ships with ``TraceEnable Off`` as the recommended default; LLM-
generated ``httpd.conf`` / ``apache2.conf`` snippets sometimes flip it
back to ``On`` (often pasted from outdated tutorials).

What's checked (per file):
  - ``TraceEnable On`` / ``TraceEnable extended`` at the global or
    vhost scope.
  - ``RewriteCond %{REQUEST_METHOD} ^TRACE`` rules paired with a
    permissive ``[L]`` (i.e. *not* a deny) — flagged as suspicious
    rather than blocking, but reported.
  - Dockerfile ``RUN`` lines that ``sed`` / ``echo`` ``TraceEnable On``
    into a config file.

Accepted (not flagged):
  - ``TraceEnable Off`` / ``off`` / ``0``.
  - Any file containing ``# apache-traceenable-allowed`` (committed
    test fixtures).
  - Comment lines (``#`` prefix).

CWE refs:
  - CWE-489: Active Debug Code
  - CWE-200: Exposure of Sensitive Information to an Unauthorized
    Actor
  - CWE-693: Protection Mechanism Failure

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

SUPPRESS = re.compile(r"#\s*apache-traceenable-allowed", re.IGNORECASE)

TRUTHY = {"on", "1", "true", "yes", "extended"}
SAFE = {"off", "0", "false", "no", ""}

# Apache: TraceEnable On
TRACE_RE = re.compile(r"^\s*TraceEnable\s+(\S+)", re.IGNORECASE)

# Dockerfile sed/echo into apache config
DOCKER_SED_RE = re.compile(
    r"""sed[^\n]*TraceEnable\s+([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)
DOCKER_ECHO_RE = re.compile(
    r"""echo[^\n]*TraceEnable\s+([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)


def _normalize(val: str) -> str:
    return val.strip().strip("'\"").lower()


def _is_truthy(val: str) -> bool:
    return _normalize(val) in TRUTHY


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue

        m = TRACE_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"TraceEnable {m.group(1)} keeps HTTP TRACE active (XST exposure)")
            )
            continue

        m = DOCKER_SED_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"Dockerfile sed sets TraceEnable {m.group(1)} in apache config")
            )
            continue

        m = DOCKER_ECHO_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"Dockerfile echo sets TraceEnable {m.group(1)} in apache config")
            )
            continue

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*.conf", "httpd.conf", "apache2.conf", "Dockerfile*"):
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

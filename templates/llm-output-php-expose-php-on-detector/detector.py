#!/usr/bin/env python3
"""Detect PHP configurations that ship with ``expose_php = On``.

When ``expose_php`` is enabled, PHP advertises its presence and version
in the ``X-Powered-By`` HTTP response header (e.g.
``X-Powered-By: PHP/8.1.4``). This hands attackers a no-cost
fingerprint they can map directly against published CVEs to pick a
working exploit. The PHP manual recommends ``expose_php = Off`` for
production. LLM-generated ``php.ini`` snippets, Dockerfiles, and
``ansible`` lineinfile fragments often leave the upstream default
``On`` in place, or pasted dev examples flip it back on.

What's checked (per file):
  - ``expose_php = On`` / ``expose_php=on`` / ``expose_php = 1`` /
    ``expose_php = true`` / ``expose_php = yes`` in any ``*.ini`` /
    ``php.ini`` style file.
  - Dockerfile ``RUN`` lines that ``sed`` or ``echo`` ``expose_php``
    set to a truthy value into a php.ini-style file.

Accepted (not flagged):
  - ``expose_php = Off`` / ``off`` / ``0`` / ``false`` / ``no``.
  - Any file containing ``# php-expose-php-allowed`` (committed test
    fixtures or intentional dev configs).
  - Comment lines (``;`` or ``#`` prefix per php.ini conventions).

CWE refs:
  - CWE-200: Exposure of Sensitive Information to an Unauthorized
    Actor
  - CWE-209: Generation of Error Message Containing Sensitive
    Information
  - CWE-497: Exposure of Sensitive System Information to an
    Unauthorized Control Sphere

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

SUPPRESS = re.compile(r"[#;]\s*php-expose-php-allowed", re.IGNORECASE)

TRUTHY = {"on", "1", "true", "yes"}

# php.ini: expose_php = On
INI_RE = re.compile(r"^\s*expose_php\s*=\s*([A-Za-z0-9_'\"-]+)", re.IGNORECASE)

# Dockerfile sed/echo into php.ini
DOCKER_SED_RE = re.compile(
    r"""sed[^\n]*expose_php\s*=\s*([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)
DOCKER_ECHO_RE = re.compile(
    r"""echo[^\n]*expose_php\s*=\s*([A-Za-z0-9_'"-]+)""",
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
        if stripped.startswith(";") or stripped.startswith("#"):
            # php.ini uses ';' for comments; Dockerfiles use '#'. We
            # still want to inspect Dockerfile RUN lines, which never
            # start with '#'. So skipping '#' lines wholesale is safe.
            continue

        m = INI_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"expose_php = {m.group(1)} leaks PHP version via X-Powered-By")
            )
            continue

        m = DOCKER_SED_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"Dockerfile sed sets expose_php = {m.group(1)} in php.ini")
            )
            continue

        m = DOCKER_ECHO_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (i, f"Dockerfile echo sets expose_php = {m.group(1)} in php.ini")
            )
            continue

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*.ini", "php.ini", "Dockerfile*"):
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

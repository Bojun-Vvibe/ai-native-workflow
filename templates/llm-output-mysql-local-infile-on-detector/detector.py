#!/usr/bin/env python3
"""Detect MySQL/MariaDB configurations that ship with
``local_infile = 1`` (or equivalent), enabling the
``LOAD DATA LOCAL INFILE`` client capability server-side.

When ``local_infile`` is enabled, a malicious or compromised MySQL
*server* can ask any connecting client to upload an arbitrary file
from the client's filesystem (the protocol allows the server to
request a file when the client opts in). When enabled on the server
side, a SQL-injection bug in any application using ``LOAD DATA LOCAL
INFILE`` (or an attacker who phishes a DBA into connecting to a
hostile server) can be turned into arbitrary file read on the client
host, including ``/etc/passwd``, application secrets, or SSH keys.

Modern MySQL (8.0+) ships with ``local_infile = OFF`` by default;
LLM-generated ``my.cnf`` snippets, Dockerfiles, and ansible
``lineinfile`` fragments often flip it back on, usually pasted from
old MySQL 5.x tutorials.

What's checked (per file):
  - ``local_infile = ON`` / ``=1`` / ``=true`` / ``=yes`` in any
    ``my.cnf`` / ``*.cnf`` / ``mysqld.cnf`` style file.
  - Dockerfile ``RUN`` lines that ``sed`` or ``echo``
    ``local_infile`` set to a truthy value into a ``my.cnf`` file.
  - mysqld command-line flags ``--local-infile`` /
    ``--local-infile=1`` in Dockerfile ``CMD`` / ``ENTRYPOINT``.

Accepted (not flagged):
  - ``local_infile = OFF`` / ``0`` / ``false`` / ``no``.
  - Any file containing ``# mysql-local-infile-allowed`` (committed
    test fixtures or intentional bulk-load hosts).
  - Comment lines (``#`` prefix per my.cnf convention).

CWE refs:
  - CWE-22: Improper Limitation of a Pathname to a Restricted
    Directory ('Path Traversal')
  - CWE-200: Exposure of Sensitive Information to an Unauthorized
    Actor
  - CWE-732: Incorrect Permission Assignment for Critical Resource

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

SUPPRESS = re.compile(r"#\s*mysql-local-infile-allowed", re.IGNORECASE)

TRUTHY = {"on", "1", "true", "yes"}

# my.cnf: local_infile = ON  (allow either '_' or '-')
CNF_RE = re.compile(
    r"^\s*local[_-]infile\s*=\s*([A-Za-z0-9_'\"-]+)",
    re.IGNORECASE,
)

# Dockerfile sed/echo into my.cnf
DOCKER_SED_RE = re.compile(
    r"""sed[^\n]*local[_-]infile\s*=\s*([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)
DOCKER_ECHO_RE = re.compile(
    r"""echo[^\n]*local[_-]infile\s*=\s*([A-Za-z0-9_'"-]+)""",
    re.IGNORECASE,
)

# mysqld --local-infile or --local-infile=1
CLI_RE = re.compile(
    r"""--local[_-]infile(?:\s*=\s*([A-Za-z0-9_'"-]+))?""",
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

        m = CNF_RE.match(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (
                    i,
                    f"local_infile = {m.group(1)} enables LOAD DATA LOCAL INFILE "
                    "(client-side file disclosure risk)",
                )
            )
            continue

        m = DOCKER_SED_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (
                    i,
                    f"Dockerfile sed sets local_infile = {m.group(1)} in my.cnf",
                )
            )
            continue

        m = DOCKER_ECHO_RE.search(raw)
        if m and _is_truthy(m.group(1)):
            findings.append(
                (
                    i,
                    f"Dockerfile echo sets local_infile = {m.group(1)} in my.cnf",
                )
            )
            continue

        m = CLI_RE.search(raw)
        if m:
            val = m.group(1)
            # Bare --local-infile (no =VAL) defaults to enabled.
            if val is None or _is_truthy(val):
                shown = val if val is not None else "(bare flag)"
                findings.append(
                    (
                        i,
                        f"mysqld --local-infile{('=' + str(val)) if val else ''} "
                        "enables LOAD DATA LOCAL INFILE",
                    )
                )
                continue
                # variable shown unused; keep flake quiet
                _ = shown

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*.cnf", "my.cnf", "mysqld.cnf", "Dockerfile*"):
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

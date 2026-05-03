#!/usr/bin/env python3
"""Detect configurations that stand up a MinIO server with the
well-known default root credentials (``MINIO_ROOT_USER=minioadmin``
/ ``MINIO_ROOT_PASSWORD=minioadmin``) or the legacy
``MINIO_ACCESS_KEY`` / ``MINIO_SECRET_KEY`` equivalents.

``minioadmin`` / ``minioadmin`` is the documented bootstrap
default when MinIO starts without credentials set; it is also the
value every quickstart blog, Stack Overflow answer, and LLM
completion copies verbatim. A MinIO server reachable on the
network with those credentials is a fully writable S3 endpoint
and a remote-code-execution surface via the admin API
(CWE-798, CWE-1392).

LLM-generated ``docker-compose.yml``, ``.env``, and shell scripts
routinely emit shapes like::

    services:
      minio:
        image: minio/minio
        environment:
          MINIO_ROOT_USER: minioadmin
          MINIO_ROOT_PASSWORD: minioadmin

or::

    export MINIO_ROOT_USER=minioadmin
    export MINIO_ROOT_PASSWORD=minioadmin

What's checked (per file):
  - Any line that binds one of
    {``MINIO_ROOT_USER``, ``MINIO_ROOT_PASSWORD``,
    ``MINIO_ACCESS_KEY``, ``MINIO_SECRET_KEY``}
    to the literal value ``minioadmin`` (with optional surrounding
    quotes).
  - Shell ``KEY=value`` form, optional leading ``export``.
  - YAML ``KEY: value`` form (typical compose ``environment:``
    block) and the ``- KEY=value`` list form.
  - Dotenv ``KEY=value`` form.

Accepted (not flagged):
  - Any non-default value (including ``minioadmin1``, ``changeme``,
    ``${MINIO_ROOT_PASSWORD}``, ``$(openssl rand -hex 16)``).
  - Lines beginning with ``#`` (shell/YAML comment).
  - Files containing the comment ``# minio-default-creds-allowed``
    are skipped wholesale (intentional local-smoke fixtures).

CWE refs:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements

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

SUPPRESS = re.compile(r"#\s*minio-default-creds-allowed", re.IGNORECASE)

CRED_KEYS = {
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
}

DEFAULT_VALUE = "minioadmin"

# Shell / dotenv:  optional `export `, KEY=value
SHELL_RE = re.compile(
    r"^\s*(?:export\s+)?(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>.+?)\s*$"
)
# YAML mapping:  KEY: value
YAML_MAP_RE = re.compile(
    r"^\s*(?P<key>[A-Z_][A-Z0-9_]*)\s*:\s*(?P<value>.+?)\s*$"
)
# YAML list item with embedded =:  - KEY=value
YAML_LIST_RE = re.compile(
    r"^\s*-\s*(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>.+?)\s*$"
)


def _strip_quotes(s: str) -> str:
    s = s.strip()
    # Strip an inline trailing comment introduced by ' #' or '\t#'.
    # Don't strip '#' inside quoted strings.
    if s and s[0] not in {'"', "'"}:
        # naive but adequate for this format set
        for marker in (" #", "\t#"):
            idx = s.find(marker)
            if idx != -1:
                s = s[:idx].rstrip()
                break
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        return s[1:-1]
    return s


def _is_default(value: str) -> bool:
    return _strip_quotes(value).strip() == DEFAULT_VALUE


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    for idx, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("#"):
            continue

        for regex in (SHELL_RE, YAML_LIST_RE, YAML_MAP_RE):
            m = regex.match(raw)
            if not m:
                continue
            key = m.group("key")
            if key not in CRED_KEYS:
                break  # matched a key shape but not a MinIO key — done
            value = m.group("value")
            if _is_default(value):
                findings.append(
                    (
                        idx,
                        f"MinIO {key} bound to default credential "
                        f'"{DEFAULT_VALUE}"',
                    )
                )
            break

    return findings


def _is_target(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith((".yml", ".yaml", ".env", ".sh", ".bash", ".envfixture")):
        return True
    if name.startswith(".env"):
        return True
    if name in {"dockerfile", "compose.yaml", "compose.yml",
               "docker-compose.yaml", "docker-compose.yml"}:
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_target(f):
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

#!/usr/bin/env python3
"""Detect rsync daemon (``rsyncd.conf``) module definitions that expose
a writable or read path with no ``auth users`` configured.

``rsyncd`` modules without an ``auth users`` line are reachable by any
client that can speak rsync to the daemon TCP port (typically 873).
Combined with ``read only = false`` this is an unauthenticated remote
file-write primitive (CWE-306 / CWE-284); even with the default
``read only = true`` it is a bulk data exfiltration channel
(CWE-200).

LLM-generated ``rsyncd.conf``, container entrypoints, and Ansible
templates routinely emit shapes like::

    [backup]
    path = /srv/backup
    read only = false
    # no auth users, no secrets file

or::

    [public]
    path = /var/www/public
    hosts allow = *

This detector parses each ``[module]`` block and flags any module
whose body lacks both ``auth users`` and a global / per-module
``secrets file`` line.

What's checked (per file):
  - INI-style ``[module]`` headers in ``rsyncd.conf`` style files.
  - Each module's body for ``auth users = ...`` (non-empty value).
  - Each module that has ``path = ...`` set but no ``auth users``.
  - Modules with ``read only = false`` are escalated in the message.
  - The global section (before any ``[module]``) is ignored for the
    "missing auth" check, but a global ``auth users`` does NOT
    propagate to modules (rsyncd does not inherit it).

Accepted (not flagged):
  - Modules with ``auth users = alice,bob`` (non-empty).
  - Files containing the comment ``# rsyncd-no-auth-allowed`` are
    skipped wholesale (e.g. intentional anonymous mirrors).
  - Modules with no ``path =`` line are treated as incomplete stubs
    and skipped.

CWE refs:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-284: Improper Access Control
  - CWE-200: Exposure of Sensitive Information to an Unauthorized
    Actor

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

SUPPRESS = re.compile(r"#\s*rsyncd-no-auth-allowed", re.IGNORECASE)

HEADER_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KV_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _-]*?)\s*=\s*(.*?)\s*$")


def _is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("#") or s.startswith(";")


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    # Collect modules: list of (name, header_line, body: list[(line, key, val)])
    modules: List[Tuple[str, int, List[Tuple[int, str, str]]]] = []
    current: Tuple[str, int, List[Tuple[int, str, str]]] | None = None

    for i, raw in enumerate(source.splitlines(), start=1):
        if _is_comment(raw):
            continue
        m = HEADER_RE.match(raw)
        if m:
            if current is not None:
                modules.append(current)
            current = (m.group(1).strip(), i, [])
            continue
        if current is None:
            continue
        kv = KV_RE.match(raw)
        if kv:
            key = kv.group(1).strip().lower()
            # collapse internal whitespace (rsyncd allows "auth users")
            key = re.sub(r"\s+", " ", key)
            val = kv.group(2).strip()
            current[2].append((i, key, val))

    if current is not None:
        modules.append(current)

    for name, header_line, body in modules:
        keys = {k: (ln, v) for ln, k, v in body}
        if "path" not in keys:
            continue  # incomplete stub
        auth = keys.get("auth users", (0, ""))[1]
        secrets = keys.get("secrets file", (0, ""))[1]
        if auth.strip():
            continue
        read_only = keys.get("read only", (0, "true"))[1].strip().lower()
        writable = read_only in {"false", "no", "0", "off"}
        msg_extra = " (writable: read only = false)" if writable else ""
        if secrets.strip():
            # secrets without auth users is meaningless in rsyncd, still flag
            findings.append(
                (
                    header_line,
                    f"rsyncd module [{name}] has secrets file but no auth users{msg_extra}",
                )
            )
        else:
            findings.append(
                (
                    header_line,
                    f"rsyncd module [{name}] missing 'auth users'{msg_extra}",
                )
            )

    return findings


def _is_rsyncd_file(path: Path) -> bool:
    name = path.name.lower()
    if name in {"rsyncd.conf", "rsyncd.secrets"}:
        return name == "rsyncd.conf"
    if name.endswith(".conf") and "rsyncd" in name:
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_rsyncd_file(f):
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

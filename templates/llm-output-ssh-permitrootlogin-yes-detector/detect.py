#!/usr/bin/env python3
"""
llm-output-ssh-permitrootlogin-yes-detector

Flags OpenSSH server configuration files (``sshd_config`` and drop-in
files under ``sshd_config.d/``) where ``PermitRootLogin`` is set to
``yes``.

Allowing direct interactive SSH login as root collapses the gap
between credential compromise and full system takeover, defeats per-
user audit trails, and contradicts the OpenSSH project's own default
(``prohibit-password``) since OpenSSH 7.0.

Maps to CWE-250 (Execution with Unnecessary Privileges) and CWE-1188
(Insecure Default Initialization of Resource).

LLMs reach for ``PermitRootLogin yes`` as a one-line fix when a user
pastes "Permission denied" from an SSH session, instead of teaching
the user to log in as a normal account and use ``sudo``.

Stdlib only. Reads files from argv. When given a directory, recurses
and inspects files whose basename is ``sshd_config`` or that live
under a ``sshd_config.d`` directory. Exit 0 = no findings,
1 = finding(s), 2 = usage error.

Per-line suppression marker:

    PermitRootLogin yes  # llm-allow:sshd-permitrootlogin
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

SUPPRESS = "llm-allow:sshd-permitrootlogin"

# Match a non-comment line that sets PermitRootLogin to yes.
# OpenSSH is case-insensitive on directive names. The value `yes` is
# matched case-insensitively too. We do NOT match other values like
# `no`, `prohibit-password`, `without-password`, or
# `forced-commands-only`.
_LINE_RE = re.compile(
    r"^\s*PermitRootLogin\s+yes\s*(?:#.*)?$",
    re.IGNORECASE,
)


def _is_sshd_config_path(path: str) -> bool:
    base = os.path.basename(path)
    if base == "sshd_config":
        return True
    if base.endswith(".sshd_config") or base.endswith("_sshd_config"):
        return True
    parts = path.replace("\\", "/").split("/")
    if "sshd_config.d" in parts:
        return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        # Strip leading whitespace to check for a comment-only line.
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if not _LINE_RE.match(line):
            continue
        if SUPPRESS in line:
            continue
        findings.append(
            f"{path}:{i}: sshd-permitrootlogin-yes: {line.rstrip()}"
        )
    return findings


def iter_paths(args: Iterable[str]) -> Iterable[str]:
    for a in args:
        if os.path.isdir(a):
            for root, _dirs, files in os.walk(a):
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    if _is_sshd_config_path(full):
                        yield full
        else:
            # Files passed explicitly are always inspected; the user
            # asked for it.
            yield a


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: List[str] = []
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        findings.extend(scan_text(text, path))
    for line in findings:
        print(line)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

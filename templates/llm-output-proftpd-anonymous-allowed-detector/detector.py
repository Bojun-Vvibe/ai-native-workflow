#!/usr/bin/env python3
"""Detect ProFTPD configurations that enable an anonymous FTP
login surface without restricting it.

ProFTPD's ``proftpd.conf`` historically ships with an ``<Anonymous>``
example block. When that block is present, uncommented, and lacks
both ``<Limit LOGIN>...DenyAll</Limit>`` and a
``RequireValidShell`` / ``AnonRequirePassword`` constraint, the
server accepts logins as ``anonymous`` / ``ftp`` (or any user
specified in the block via ``User``) **with no password validation
beyond the email-as-password convention**, and then exposes whatever
directory the anonymous user maps to.

Operationally this is the textbook CWE-284 (Improper Access
Control) / CWE-287 (Improper Authentication) finding for FTP, and
it shows up routinely in LLM-generated ProFTPD snippets like::

    <Anonymous ~ftp>
      User ftp
      Group ftp
      UserAlias anonymous ftp
      <Limit WRITE>
        DenyAll
      </Limit>
    </Anonymous>

…where the LOGIN limit is *not* declared, so the block effectively
permits anyone to log in. Same shape applies to copies that allow
``WRITE`` for anonymous (turning the box into open file storage)
or that omit ``RequireValidShell off`` notes entirely.

What's checked, per file:

  - The file contains an active (uncommented) ``<Anonymous ...>``
    block that is properly closed by ``</Anonymous>``.
  - Inside that block, NONE of the following anonymous-hardening
    directives appear (case-insensitive, on an active line):
      * ``<Limit LOGIN>`` paired with ``DenyAll`` / ``DenyUser``
        / ``DenyGroup``.
      * ``AnonRequirePassword on``.
      * ``RequireValidShell on`` together with a non-``ftp``
        ``User`` directive.

If multiple ``<Anonymous>`` blocks exist, each is evaluated
independently and any unhardened block causes a finding.

Accepted (not flagged):

  - File has no ``<Anonymous>`` block, or all such blocks are
    fully commented out.
  - ``<Anonymous>`` block contains a ``<Limit LOGIN>`` ... ``DenyAll``
    pair (anonymous logins explicitly denied).
  - ``<Anonymous>`` block contains ``AnonRequirePassword on``.
  - File contains the comment ``# proftpd-anonymous-allowed``
    (intentional public-archive override, e.g. read-only mirror).

Usage::

    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at
255). Stdout: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*proftpd-anonymous-allowed", re.IGNORECASE)

ANON_OPEN_RE = re.compile(r"^\s*<\s*Anonymous\b[^>]*>", re.IGNORECASE)
ANON_CLOSE_RE = re.compile(r"^\s*</\s*Anonymous\s*>", re.IGNORECASE)
LIMIT_LOGIN_OPEN_RE = re.compile(
    r"^\s*<\s*Limit\b[^>]*\bLOGIN\b[^>]*>", re.IGNORECASE
)
LIMIT_CLOSE_RE = re.compile(r"^\s*</\s*Limit\s*>", re.IGNORECASE)
DENY_RE = re.compile(
    r"^\s*(DenyAll|DenyUser\b|DenyGroup\b)", re.IGNORECASE
)
ANON_REQ_PW_RE = re.compile(
    r"^\s*AnonRequirePassword\s+on\b", re.IGNORECASE
)


def _line_is_active(raw: str) -> bool:
    s = raw.lstrip()
    if not s:
        return False
    if s.startswith("#"):
        return False
    return True


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()
    n = len(lines)

    i = 0
    while i < n:
        raw = lines[i]
        if _line_is_active(raw) and ANON_OPEN_RE.match(raw):
            anon_start = i + 1
            block_lines: List[Tuple[int, str]] = []
            j = i + 1
            closed = False
            while j < n:
                if _line_is_active(lines[j]) and ANON_CLOSE_RE.match(
                    lines[j]
                ):
                    closed = True
                    break
                block_lines.append((j + 1, lines[j]))
                j += 1
            if not closed:
                # Unterminated -> conservative: skip.
                i = j
                continue

            hardened = _block_is_hardened(block_lines)
            if not hardened:
                findings.append(
                    (
                        anon_start,
                        "ProFTPD <Anonymous> block without "
                        "<Limit LOGIN>DenyAll</Limit> or "
                        "AnonRequirePassword on (CWE-284/CWE-287)",
                    )
                )
            i = j + 1
            continue
        i += 1
    return findings


def _block_is_hardened(block_lines: List[Tuple[int, str]]) -> bool:
    in_login_limit = False
    login_limit_denies = False
    for _, raw in block_lines:
        if not _line_is_active(raw):
            continue
        if ANON_REQ_PW_RE.match(raw):
            return True
        if LIMIT_LOGIN_OPEN_RE.match(raw):
            in_login_limit = True
            continue
        if in_login_limit and LIMIT_CLOSE_RE.match(raw):
            in_login_limit = False
            continue
        if in_login_limit and DENY_RE.match(raw):
            login_limit_denies = True
    return login_limit_denies


def _is_proftpd_conf(path: Path) -> bool:
    name = path.name.lower()
    if name in {"proftpd.conf", "proftpd.conf.dist"}:
        return True
    if name.endswith(".conf"):
        return True
    if name.endswith(".include"):
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_proftpd_conf(f):
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

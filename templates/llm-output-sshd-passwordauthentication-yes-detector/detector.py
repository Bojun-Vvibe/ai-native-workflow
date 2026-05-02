#!/usr/bin/env python3
"""Detect OpenSSH server configuration files (``sshd_config`` and
``sshd_config.d/*.conf``) that leave password authentication enabled.

Background
----------
On a default OpenSSH install ``PasswordAuthentication`` is ``yes``.
That single line is the difference between "an attacker needs to
steal a private key from a developer laptop" and "an attacker can
spray every leaked credential from the latest combolist against
your bastion until something sticks". Every public-internet sshd
should be key-only.

The hardened recipe is::

    PasswordAuthentication no
    KbdInteractiveAuthentication no
    ChallengeResponseAuthentication no
    UsePAM yes
    PermitEmptyPasswords no

LLMs frequently emit ``sshd_config`` snippets that:

* explicitly write ``PasswordAuthentication yes`` (often "to make
  it easier to log in for testing"),
* leave ``PasswordAuthentication`` unset on a config that clearly
  *is* a server config (has ``Port``, ``ListenAddress``,
  ``HostKey``, or ``AuthorizedKeysFile``), so the OpenSSH default
  of ``yes`` silently applies,
* disable password auth but then re-enable it with
  ``KbdInteractiveAuthentication yes`` /
  ``ChallengeResponseAuthentication yes``, which on a stock PAM
  stack is functionally equivalent to password auth,
* set ``PermitEmptyPasswords yes`` (catastrophic),
* set ``PasswordAuthentication no`` only inside a ``Match`` block
  that gates on a single user/group, leaving the global default
  ``yes``.

What's flagged
--------------
Per file, line-level findings:

* ``PasswordAuthentication yes``
* ``KbdInteractiveAuthentication yes``
* ``ChallengeResponseAuthentication yes``
* ``PermitEmptyPasswords yes``

Whole-file finding (line 0):

* The file looks like a top-level sshd server config (contains
  ``Port``, ``ListenAddress``, ``HostKey``, ``AuthorizedKeysFile``,
  ``Subsystem``, or ``HostKeyAlgorithms`` *outside* any ``Match``
  block) AND it never sets ``PasswordAuthentication no`` at the
  top level. A ``PasswordAuthentication no`` that lives only inside
  a ``Match`` block does NOT count — the global default ``yes``
  still applies.

What's NOT flagged
------------------
* ``PasswordAuthentication no`` at top level.
* Drop-in fragments that contain only ``Match`` blocks and no
  top-level server-identity directives.
* Lines with a trailing ``# sshd-pw-ok`` comment.
* Files containing ``sshd-pw-ok-file`` in any comment.

Refs
----
* CWE-521: Weak Password Requirements
* CWE-307: Improper Restriction of Excessive Authentication Attempts
* CIS Benchmark for Linux — sshd PasswordAuthentication
* OpenSSH ``sshd_config(5)`` — PasswordAuthentication,
  KbdInteractiveAuthentication, PermitEmptyPasswords

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*sshd-pw-ok\b")
SUPPRESS_FILE = re.compile(r"sshd-pw-ok-file\b")

PW_YES = re.compile(r"^\s*PasswordAuthentication\s+yes\b", re.IGNORECASE)
PW_NO = re.compile(r"^\s*PasswordAuthentication\s+no\b", re.IGNORECASE)
KBD_YES = re.compile(r"^\s*KbdInteractiveAuthentication\s+yes\b", re.IGNORECASE)
CHAL_YES = re.compile(r"^\s*ChallengeResponseAuthentication\s+yes\b", re.IGNORECASE)
EMPTY_YES = re.compile(r"^\s*PermitEmptyPasswords\s+yes\b", re.IGNORECASE)
MATCH_BLOCK = re.compile(r"^\s*Match\s+", re.IGNORECASE)

TOP_LEVEL_HINT = re.compile(
    r"^\s*(Port\s+|ListenAddress\s+|HostKey\s+|AuthorizedKeysFile\s+|Subsystem\s+|HostKeyAlgorithms\s+)",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings

    has_pw_no_top = False
    in_match = False
    has_top_level_hint = False

    for i, raw in enumerate(source.splitlines(), start=1):
        body = _strip_comment(raw)

        if MATCH_BLOCK.match(body):
            in_match = True
            continue

        # A non-indented, non-Match directive ends the prior Match block
        # in OpenSSH. We approximate: any line that is left-flush and
        # contains a recognized directive resets in_match.
        if body.strip() and not body.startswith((" ", "\t")):
            if not MATCH_BLOCK.match(body):
                in_match = False

        if SUPPRESS_LINE.search(raw):
            if PW_NO.match(body) and not in_match:
                has_pw_no_top = True
            continue

        if not in_match and TOP_LEVEL_HINT.match(body):
            has_top_level_hint = True

        if PW_YES.match(body):
            findings.append(
                (
                    i,
                    "`PasswordAuthentication yes` enables credential-spray attacks against sshd",
                )
            )
            continue
        if KBD_YES.match(body):
            findings.append(
                (
                    i,
                    "`KbdInteractiveAuthentication yes` re-enables password prompt via PAM",
                )
            )
            continue
        if CHAL_YES.match(body):
            findings.append(
                (
                    i,
                    "`ChallengeResponseAuthentication yes` re-enables password prompt via PAM",
                )
            )
            continue
        if EMPTY_YES.match(body):
            findings.append(
                (i, "`PermitEmptyPasswords yes` lets accounts with empty passwords log in")
            )
            continue
        if PW_NO.match(body) and not in_match:
            has_pw_no_top = True

    # Re-scan top-level hint independent of Match (cheap)
    if not has_top_level_hint:
        # fall back: any of the hint patterns anywhere
        has_top_level_hint = bool(TOP_LEVEL_HINT.search(source))

    if has_top_level_hint and not has_pw_no_top:
        if not any(line == 0 for line, _ in findings):
            findings.append(
                (
                    0,
                    "top-level sshd_config has no `PasswordAuthentication no` — OpenSSH default `yes` applies",
                )
            )

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "sshd_config",
        "sshd_config.d/*.conf",
        "*.sshd.conf",
        "ssh/sshd_config*",
    )
    for pattern in patterns:
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

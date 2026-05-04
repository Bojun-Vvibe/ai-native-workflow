#!/usr/bin/env python3
"""Detect Vaultwarden deployment configurations from LLM output that
leave open public sign-up (``SIGNUPS_ALLOWED=true``) without any of
the gating mitigations (domain allow-list, invitations-only, admin
token).

Vaultwarden's default for ``SIGNUPS_ALLOWED`` is **true** — the
"first-run" UX hands the deployer an account immediately. The
upstream README is explicit that this should be flipped to ``false``
once the operator account exists, but LLMs replicate the
quickstart compose file verbatim and ship the resulting deployment
to the public internet, where any visitor can mint accounts and
consume storage / send invitation email at the operator's expense.

This detector scans a config blob (env file, docker-compose snippet,
k8s manifest, helm values, systemd EnvironmentFile, raw shell) and
flags the unsafe shapes:

  1. ``SIGNUPS_ALLOWED=true`` (or unquoted ``True``/``yes``/``1``)
     with no ``SIGNUPS_DOMAINS_WHITELIST`` set.
  2. ``SIGNUPS_ALLOWED=true`` with an empty
     ``SIGNUPS_DOMAINS_WHITELIST=""`` (whitelist treated as
     "all domains").
  3. ``SIGNUPS_ALLOWED=true`` together with
     ``SIGNUPS_VERIFY=false`` (no email verification gate).
  4. ``SIGNUPS_ALLOWED=true`` together with ``ADMIN_TOKEN=""`` /
     missing admin token (no admin panel to disable signups
     after initial bootstrap).

Suppression: a top-level comment ``# vaultwarden-signups-allowed-ok``
skips the file (e.g. for a deliberate public family-wallet demo).

CWE-1188 (Insecure Default Initialization of Resource) and
CWE-862 (Missing Authorization) apply.

Public API:
    scan(text: str) -> list[tuple[int, str]]
        Returns a list of (line_number_1based, reason) tuples.
        Empty list = clean.

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*vaultwarden-signups-allowed-ok", re.IGNORECASE)

TRUE_VALUES = {"true", "yes", "1", "on"}
FALSE_VALUES = {"false", "no", "0", "off"}


def _env_re(name: str) -> re.Pattern:
    return re.compile(
        r"""(?ix)
        (?:^|[\s,;])
        (?:export\s+)?
        """
        + name
        + r"""
        \s*[:=]\s*
        (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
        """,
    )


SIGNUPS_ALLOWED = _env_re("SIGNUPS_ALLOWED")
SIGNUPS_WHITELIST = _env_re("SIGNUPS_DOMAINS_WHITELIST")
SIGNUPS_VERIFY = _env_re("SIGNUPS_VERIFY")
ADMIN_TOKEN = _env_re("ADMIN_TOKEN")


def _strip(v: Optional[str]) -> str:
    if v is None:
        return ""
    return v.strip().strip("'\"")


def _is_true(v: str) -> bool:
    return v.strip().lower() in TRUE_VALUES


def _is_false(v: str) -> bool:
    return v.strip().lower() in FALSE_VALUES


def _line_for(lines: List[str], pat: re.Pattern) -> int:
    for i, ln in enumerate(lines, start=1):
        if pat.search(ln):
            return i
    return 1


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    lines = text.splitlines()
    findings: List[Tuple[int, str]] = []

    sa_match = SIGNUPS_ALLOWED.search(text)
    if sa_match is None:
        # SIGNUPS_ALLOWED is absent. Vaultwarden defaults to true,
        # but if the file does not mention sign-ups at all we have
        # nothing to flag (treat as out-of-scope to avoid false
        # positives on unrelated configs).
        return []
    sa_value = _strip(sa_match.group("val"))
    if not _is_true(sa_value):
        return []

    sa_line = _line_for(lines, SIGNUPS_ALLOWED)

    # Rule 1 / 2: whitelist.
    wl_match = SIGNUPS_WHITELIST.search(text)
    if wl_match is None:
        findings.append(
            (
                sa_line,
                "SIGNUPS_ALLOWED=true with no SIGNUPS_DOMAINS_WHITELIST "
                "(public registration open to any email domain)",
            )
        )
    else:
        wl_value = _strip(wl_match.group("val"))
        if wl_value == "":
            findings.append(
                (
                    _line_for(lines, SIGNUPS_WHITELIST),
                    "SIGNUPS_DOMAINS_WHITELIST is empty while SIGNUPS_ALLOWED=true "
                    "(empty whitelist is treated as 'all domains')",
                )
            )

    # Rule 3: signup verification.
    sv_match = SIGNUPS_VERIFY.search(text)
    if sv_match is not None:
        sv_value = _strip(sv_match.group("val"))
        if _is_false(sv_value):
            findings.append(
                (
                    _line_for(lines, SIGNUPS_VERIFY),
                    "SIGNUPS_VERIFY=false with SIGNUPS_ALLOWED=true "
                    "(no email verification gate on public sign-up)",
                )
            )

    # Rule 4: admin token absent / empty.
    at_match = ADMIN_TOKEN.search(text)
    if at_match is None:
        findings.append(
            (
                sa_line,
                "SIGNUPS_ALLOWED=true with no ADMIN_TOKEN set "
                "(no admin panel to disable signups after bootstrap)",
            )
        )
    else:
        at_value = _strip(at_match.group("val"))
        if at_value == "":
            findings.append(
                (
                    _line_for(lines, ADMIN_TOKEN),
                    "ADMIN_TOKEN is empty while SIGNUPS_ALLOWED=true "
                    "(admin panel disabled, cannot revoke open signups)",
                )
            )

    # de-dup while preserving order
    seen: set = set()
    unique: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        unique.append(f)
    return unique


def _scan_path(p: Path) -> int:
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{p}:0:read-error: {exc}")
        return 0
    hits = scan(text)
    for line, reason in hits:
        print(f"{p}:{line}:{reason}")
    return 1 if hits else 0


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    n = 0
    for a in argv[1:]:
        n += _scan_path(Path(a))
    return min(255, n)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Detect n8n self-hosted deployment configurations from LLM output
that leave the editor / REST API without authentication.

n8n is a workflow-automation server. Self-hosted deployments are
gated by an HTTP basic-auth pair (``N8N_BASIC_AUTH_USER`` /
``N8N_BASIC_AUTH_PASSWORD``) only when ``N8N_BASIC_AUTH_ACTIVE`` is
set to ``true``. The default is **false** — if an LLM emits a
docker-compose snippet that copies the upstream "minimal" example
verbatim, the editor (which holds long-lived OAuth tokens, API
keys, SMTP credentials, and database DSNs for every connected
service) is reachable to anyone who can hit the port.

This detector flags four orthogonal regressions:

  1. ``N8N_BASIC_AUTH_ACTIVE=false`` (or any falsy synonym) without
     any other gating mechanism declared.
  2. ``N8N_BASIC_AUTH_ACTIVE`` absent entirely while the deployment
     is configured for non-local exposure (``N8N_HOST`` set to
     something other than ``localhost``/``127.0.0.1``, or
     ``N8N_TUNNEL=true``).
  3. ``N8N_BASIC_AUTH_ACTIVE=true`` but ``N8N_BASIC_AUTH_PASSWORD``
     is empty / missing — basic auth is wired up but with an empty
     password, which n8n still accepts.
  4. ``N8N_BASIC_AUTH_ACTIVE=true`` with the well-known default
     password literal ``changeme`` / ``password`` / ``admin`` /
     ``n8n`` (any case).

Truthy synonyms (``true`` / ``yes`` / ``1`` / ``on``, any case) are
all treated as enabled. Falsy synonyms (``false`` / ``no`` / ``0``
/ ``off``) are treated as disabled.

Suppression: a top-level ``# n8n-basic-auth-disabled-ok`` comment
in the file disables all rules (use only for an isolated lab
deployment that is firewalled off the public internet).

CWE refs: CWE-306 (Missing Authentication for Critical Function),
CWE-1188 (Insecure Default Initialization of Resource).

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

SUPPRESS = re.compile(r"#\s*n8n-basic-auth-disabled-ok", re.IGNORECASE)

TRUE_VALUES = {"true", "yes", "1", "on"}
FALSE_VALUES = {"false", "no", "0", "off"}

DEFAULT_PASSWORDS = {"changeme", "password", "admin", "n8n", "secret", "123456"}

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0", "::1"}


def _env_re(name: str) -> re.Pattern:
    return re.compile(
        r"""(?ix)
        (?:^|[\s,;])
        (?:export\s+)?
        """
        + name
        + r"""
        [ \t]*[:=][ \t]*
        (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
        """,
    )


BA_ACTIVE = _env_re("N8N_BASIC_AUTH_ACTIVE")
BA_USER = _env_re("N8N_BASIC_AUTH_USER")
BA_PASS = _env_re("N8N_BASIC_AUTH_PASSWORD")
N8N_HOST = _env_re("N8N_HOST")
N8N_TUNNEL = _env_re("N8N_TUNNEL")


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


def _is_local_host_value(v: str) -> bool:
    v = v.strip().lower()
    if v == "":
        return True  # nothing declared, assume local default
    return v in LOCAL_HOSTS


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    lines = text.splitlines()
    findings: List[Tuple[int, str]] = []

    active_match = BA_ACTIVE.search(text)
    host_match = N8N_HOST.search(text)
    tunnel_match = N8N_TUNNEL.search(text)

    host_value = _strip(host_match.group("val")) if host_match else ""
    tunnel_value = _strip(tunnel_match.group("val")) if tunnel_match else ""
    is_publicly_exposed = (not _is_local_host_value(host_value)) or _is_true(tunnel_value)

    # If the file does not mention n8n at all, it is out of scope. We
    # use the presence of any N8N_* key as the trigger.
    if active_match is None and host_match is None and tunnel_match is None:
        return []

    if active_match is None:
        # Rule 2: BASIC_AUTH_ACTIVE absent on a publicly-exposed setup.
        if is_publicly_exposed:
            anchor = host_match if host_match is not None else tunnel_match
            line = _line_for(lines, N8N_HOST if host_match is not None else N8N_TUNNEL)
            findings.append(
                (
                    line,
                    "N8N_BASIC_AUTH_ACTIVE not set while n8n is exposed beyond "
                    "localhost (default is false; editor and REST API are reachable "
                    "without auth)",
                )
            )
        return findings

    active_value = _strip(active_match.group("val"))
    active_line = _line_for(lines, BA_ACTIVE)

    if _is_false(active_value):
        # Rule 1: explicitly disabled.
        findings.append(
            (
                active_line,
                "N8N_BASIC_AUTH_ACTIVE=false (editor and REST API exposed without "
                "authentication; long-lived workflow credentials reachable to anyone "
                "who can connect)",
            )
        )
        return findings

    if not _is_true(active_value):
        # Unknown value; treat conservatively only if publicly exposed.
        if is_publicly_exposed:
            findings.append(
                (
                    active_line,
                    f"N8N_BASIC_AUTH_ACTIVE has unrecognised value {active_value!r} "
                    "(neither truthy nor falsy); n8n will treat as disabled",
                )
            )
        return findings

    # active is true: check password sanity (rules 3 and 4).
    pw_match = BA_PASS.search(text)
    if pw_match is None:
        findings.append(
            (
                active_line,
                "N8N_BASIC_AUTH_ACTIVE=true but N8N_BASIC_AUTH_PASSWORD is not set "
                "(empty password is accepted)",
            )
        )
    else:
        pw_value = _strip(pw_match.group("val"))
        pw_line = _line_for(lines, BA_PASS)
        if pw_value == "":
            findings.append(
                (
                    pw_line,
                    "N8N_BASIC_AUTH_PASSWORD is empty while N8N_BASIC_AUTH_ACTIVE=true "
                    "(empty password is accepted)",
                )
            )
        elif pw_value.lower() in DEFAULT_PASSWORDS:
            findings.append(
                (
                    pw_line,
                    f"N8N_BASIC_AUTH_PASSWORD is a well-known default ({pw_value!r}); "
                    "rotate before exposing the editor",
                )
            )

    return findings


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

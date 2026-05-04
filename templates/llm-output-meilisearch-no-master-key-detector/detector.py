#!/usr/bin/env python3
"""Detect Meilisearch deployment configurations from LLM output that
expose the HTTP API without a usable master key.

Meilisearch's HTTP API is **unauthenticated** unless the server is
started with a ``MEILI_MASTER_KEY`` (env var) or ``--master-key``
(CLI flag) of at least 16 bytes. From v1.0 onward the daemon will
refuse to boot in ``MEILI_ENV=production`` without one, but LLMs
routinely emit ``MEILI_ENV=development`` (or omit it, which still
leaves the dashboard wide open) and ship the resulting compose /
helm chart to the public internet.

This detector scans a config blob (env file, docker-compose snippet,
k8s manifest, helm values, systemd EnvironmentFile, raw shell) and
flags the unsafe shapes:

  1. ``MEILI_MASTER_KEY`` absent while ``MEILI_HTTP_ADDR`` /
     ``--http-addr`` is bound to a non-loopback address.
  2. ``MEILI_MASTER_KEY=""`` / ``MEILI_MASTER_KEY=''`` /
     ``MEILI_MASTER_KEY=`` (explicit empty value).
  3. ``MEILI_MASTER_KEY`` shorter than 16 bytes (Meilisearch warns
     and effectively disables key validation in dev mode).
  4. ``MEILI_ENV=development`` while a non-loopback ``MEILI_HTTP_ADDR``
     is set (development mode exposes the unauthenticated dashboard).

Suppression: a top-level comment ``# meili-no-master-key-allowed``
skips the file (e.g. local dev fixtures bound to 127.0.0.1).

CWE-306 (Missing Authentication for Critical Function) and CWE-521
(Weak Password Requirements) apply.

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

SUPPRESS = re.compile(r"#\s*meili-no-master-key-allowed", re.IGNORECASE)

LOOPBACK = {"127.0.0.1", "::1", "localhost", "[::1]", "0:0:0:0:0:0:0:1"}

# Recognises both env-var style (KEY=value, KEY: value) and CLI flags.
ENV_KEY = re.compile(
    r"""(?ix)
    (?:^|[\s,;])
    (?:export\s+)?
    MEILI_MASTER_KEY
    \s*[:=]\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
    """,
)
CLI_KEY = re.compile(r"--master-key[=\s]+(?P<val>\"[^\"]*\"|'[^']*'|\S+)")

ENV_ADDR = re.compile(
    r"""(?ix)
    (?:^|[\s,;])
    (?:export\s+)?
    MEILI_HTTP_ADDR
    \s*[:=]\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
    """,
)
CLI_ADDR = re.compile(r"--http-addr[=\s]+(?P<val>\"[^\"]*\"|'[^']*'|\S+)")

ENV_ENV = re.compile(
    r"""(?ix)
    (?:^|[\s,;])
    (?:export\s+)?
    MEILI_ENV
    \s*[:=]\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s#,;]*)
    """,
)
CLI_ENV = re.compile(r"--env[=\s]+(?P<val>\"[^\"]*\"|'[^']*'|\S+)")


def _strip(v: Optional[str]) -> str:
    if v is None:
        return ""
    return v.strip().strip("'\"")


def _bind_is_loopback(addr: str) -> bool:
    addr = _strip(addr)
    if addr == "":
        # Meilisearch defaults to 127.0.0.1:7700 when unset.
        return True
    host = addr
    # Strip port. IPv6 with brackets first.
    if host.startswith("["):
        end = host.find("]")
        if end > 0:
            host = host[1:end]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    if host == "":
        return False
    return host in LOOPBACK


def _find_line(lines: List[str], pattern: re.Pattern) -> int:
    for i, ln in enumerate(lines, start=1):
        if pattern.search(ln):
            return i
    return 1


def _first_match(text: str, *patterns: re.Pattern) -> Optional[re.Match]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m
    return None


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    lines = text.splitlines()
    findings: List[Tuple[int, str]] = []

    addr_match = _first_match(text, ENV_ADDR, CLI_ADDR)
    key_match = _first_match(text, ENV_KEY, CLI_KEY)
    env_match = _first_match(text, ENV_ENV, CLI_ENV)

    addr_value = _strip(addr_match.group("val")) if addr_match else ""
    addr_is_loopback = _bind_is_loopback(addr_value)
    addr_explicit = addr_match is not None and not addr_is_loopback

    # Helper to get reporting line for a regex match.
    def _line_for(pat: re.Pattern, fallback: int = 1) -> int:
        return _find_line(lines, pat)

    # Rule 1 + 2: no key OR empty key, while HTTP_ADDR is non-loopback.
    if addr_explicit:
        if key_match is None:
            findings.append(
                (
                    _line_for(ENV_ADDR if addr_match.re is ENV_ADDR else CLI_ADDR),
                    f"MEILI_HTTP_ADDR={addr_value} is non-loopback but no "
                    f"MEILI_MASTER_KEY / --master-key is set (HTTP API is unauthenticated)",
                )
            )
        else:
            kv = _strip(key_match.group("val"))
            if kv == "":
                findings.append(
                    (
                        _line_for(key_match.re),
                        "MEILI_MASTER_KEY is set to an empty value "
                        "(HTTP API is unauthenticated)",
                    )
                )
            elif len(kv) < 16:
                findings.append(
                    (
                        _line_for(key_match.re),
                        f"MEILI_MASTER_KEY is only {len(kv)} bytes; Meilisearch "
                        f"requires >=16 bytes and treats shorter keys as dev-mode "
                        f"(no key validation)",
                    )
                )

    # Rule 4: dev env + non-loopback bind exposes the unauthenticated dashboard.
    if env_match is not None and addr_explicit:
        env_value = _strip(env_match.group("val")).lower()
        if env_value == "development":
            findings.append(
                (
                    _line_for(env_match.re),
                    "MEILI_ENV=development with non-loopback MEILI_HTTP_ADDR "
                    "exposes the unauthenticated search preview dashboard",
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

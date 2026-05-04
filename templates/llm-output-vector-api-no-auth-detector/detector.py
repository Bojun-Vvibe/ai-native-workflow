#!/usr/bin/env python3
"""Detect Vector (the observability data pipeline by Datadog) configs
from LLM output that expose the management API without any network
restriction.

Vector ships a built-in HTTP API enabled with::

    [api]
    enabled = true
    address = "0.0.0.0:8686"
    playground = true

The API has **no authentication and no authorization** — anyone who
can reach the address can:

  * read every component's config and metrics,
  * issue GraphQL subscriptions over the live data flowing through the
    pipeline (which often carries logs with secrets),
  * load the GraphQL playground at ``/playground`` and explore.

LLMs commonly emit ``address = "0.0.0.0:8686"`` because that's what
the upstream "enable the API" snippet says. Combined with the typical
container deployment (port published, no network policy), this puts a
zero-auth introspection plane on the network.

This detector flags four orthogonal regressions:

  1. ``[api]`` table with ``enabled = true`` and ``address`` bound to
     a non-loopback host (TOML).
  2. ``api: { enabled: true, address: "0.0.0.0:..." }`` in YAML /
     JSON-ish form.
  3. ``playground = true`` while ``address`` is non-loopback (the
     playground is an unauthenticated GraphQL UI; it should never be
     reachable off-host).
  4. CLI / docker invocation: ``vector --api-address 0.0.0.0:8686``
     (or any non-loopback bind) without an external auth proxy
     declared in the same blob.

Suppression: a top-level comment ``# vector-api-public-allowed``
disables every rule (e.g. local dev fixtures behind a host-only
network).

CWE-306 (Missing Authentication for Critical Function) and CWE-732
(Incorrect Permission Assignment for Critical Resource) apply.

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
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*vector-api-public-allowed", re.IGNORECASE)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "[::1]"}

# --- TOML / YAML / inline detection helpers ---

# A boolean assignment in TOML or YAML or inline JSON form.
# Captures: key, value (true/false)
BOOL_ASSIGN = re.compile(
    r"\b(enabled|playground)\s*[:=]\s*(['\"]?)(true|false)\2",
    re.IGNORECASE,
)
# An address assignment in any of the above forms.
ADDRESS_ASSIGN = re.compile(
    r"\baddress\s*[:=]\s*['\"]([^'\"]+)['\"]"
)

# Section header for [api] in TOML.
API_SECTION_TOML = re.compile(r"^\s*\[api\]\s*$", re.MULTILINE)
# Top-level YAML block start.
API_SECTION_YAML = re.compile(r"^api\s*:\s*$", re.MULTILINE)

# Vector CLI invocation marker.
VECTOR_INVOCATION = re.compile(r"\bvector\b(?!-).*?--", re.DOTALL)
# Require the address to look like a real bind: either contain a
# port (:digits) or be a bracketed IPv6 / IPv4 dotted form.
API_ADDR_FLAG = re.compile(
    r"--api-address[=\s]+(['\"]?)"
    r"((?:\[[^\]]+\](?::\d+)?|[A-Za-z0-9_.\-]+:\d+|\d{1,3}(?:\.\d{1,3}){3}))"
    r"\1"
)


def _host_is_loopback(addr: str) -> bool:
    addr = addr.strip().strip("'\"")
    host = addr
    if host.startswith("["):
        end = host.find("]")
        if end > 0:
            host = host[1:end]
    elif ":" in host and host.count(":") == 1:
        host = host.split(":", 1)[0]
    if host == "":
        return False
    return host in LOOPBACK_HOSTS


def _block_text(text: str, header_match: re.Match[str]) -> Tuple[str, int]:
    """Return (block_text, block_start_offset) for the section
    starting at header_match. Block ends at the next blank-then-table
    boundary or another top-level section."""
    start = header_match.end()
    rest = text[start:]
    # Stop at the next section header line.
    stop = re.search(
        r"\n(?:\[[^\]]+\]\s*\n|[A-Za-z_][A-Za-z0-9_]*\s*:\s*\n)",
        rest,
    )
    if stop:
        return rest[: stop.start()], start
    return rest, start


def _line_no(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _scan_api_block(text: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    headers: List[Tuple[int, re.Match[str]]] = []
    for m in API_SECTION_TOML.finditer(text):
        headers.append((1, m))
    for m in API_SECTION_YAML.finditer(text):
        headers.append((2, m))

    for kind, header in headers:
        block, block_start = _block_text(text, header)
        bools = {
            k.group(1).lower(): (k.group(3).lower() == "true", block_start + k.start())
            for k in BOOL_ASSIGN.finditer(block)
        }
        addr_match = ADDRESS_ASSIGN.search(block)
        addr_value = addr_match.group(1) if addr_match else None
        addr_offset = block_start + addr_match.start() if addr_match else None

        enabled, enabled_off = bools.get("enabled", (False, None))
        playground, playground_off = bools.get("playground", (False, None))

        if not enabled:
            continue

        # Default address for vector when only enabled=true: 127.0.0.1:8686 (safe).
        # Only flag when an address is explicitly set to a non-loopback host.
        if addr_value is not None and not _host_is_loopback(addr_value):
            findings.append(
                (
                    _line_no(text, addr_offset),
                    f"vector [api] enabled with address={addr_value} "
                    f"(no built-in auth — anyone reachable can read every "
                    f"component's config, metrics, and live event stream)",
                )
            )
            if playground:
                findings.append(
                    (
                        _line_no(text, playground_off),
                        "vector [api].playground=true while address is "
                        "non-loopback (unauthenticated GraphQL playground "
                        "exposed)",
                    )
                )
    return findings


def _scan_cli(text: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if not re.search(r"\bvector\b", text):
        return findings
    for m in API_ADDR_FLAG.finditer(text):
        addr = m.group(2)
        if _host_is_loopback(addr):
            continue
        findings.append(
            (
                _line_no(text, m.start()),
                f"vector --api-address {addr} binds the unauthenticated "
                f"management API to a non-loopback host",
            )
        )
    return findings


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    findings: List[Tuple[int, str]] = []
    findings.extend(_scan_api_block(text))
    findings.extend(_scan_cli(text))
    seen: set[Tuple[int, str]] = set()
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

#!/usr/bin/env python3
"""Detect Grafana Mimir / Loki / Tempo configurations from LLM output
that disable multi-tenancy ("auth_enabled: false") on a deployment
that is exposed beyond loopback.

Mimir's documented "getting started" config sets::

    multitenancy_enabled: false   # or
    auth_enabled: false

Both options collapse all incoming requests onto a hard-coded ``fake``
tenant, removing the ``X-Scope-OrgID`` requirement. When the
component is reachable beyond ``127.0.0.1`` (k8s Service of type
LoadBalancer/NodePort, ``-server.http-listen-address=0.0.0.0`` flag,
or any ingress), every reader/writer can read or overwrite every
other tenant's series.

LLMs frequently keep the getting-started shape because it "just
works" without auth headers. This detector flags that shape.

Rules:

  1. ``auth_enabled: false`` (top-level, Mimir/Loki/Tempo all use
     this key) when no top-level ``# multitenancy-disabled-allowed``
     suppression comment is present.
  2. ``multitenancy_enabled: false`` (Mimir 2.x renamed key).
  3. CLI / args list with ``-auth.multitenancy-enabled=false``
     while ``-server.http-listen-address`` resolves to a non-loopback
     bind.
  4. Helm values: ``mimir.structuredConfig.auth_enabled: false``
     under any chart.

Suppression:
  - Top-level ``# multitenancy-disabled-allowed`` comment in the
    YAML/INI file.
  - Per-line ``# multitenancy-disabled-allowed`` trailing comment on
    the offending line.

CWE refs: CWE-862 (Missing Authorization), CWE-639 (Authorization
Bypass Through User-Controlled Key — the ``X-Scope-OrgID`` header
becomes a self-asserted tenant claim).

Public API:
    scan(text: str) -> list[tuple[int, str]]

CLI:
    python3 detector.py <file> [<file> ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS_FILE = re.compile(r"#\s*multitenancy-disabled-allowed", re.IGNORECASE)
SUPPRESS_LINE = re.compile(r"#\s*multitenancy-disabled-allowed", re.IGNORECASE)

LOOPBACK = {"127.0.0.1", "::1", "localhost", "[::1]", ""}

AUTH_DISABLED_RE = re.compile(
    r"^\s*(auth_enabled|multitenancy_enabled)\s*:\s*(false|no|0)\s*(#.*)?$",
    re.IGNORECASE,
)
HELM_NESTED_RE = re.compile(
    r"^\s*(auth_enabled|multitenancy_enabled)\s*:\s*(false|no|0)\b",
    re.IGNORECASE,
)
CLI_AUTH_FLAG = re.compile(
    r"-auth\.multitenancy-enabled[=\s]+(false|0|no)\b", re.IGNORECASE
)
CLI_BIND_FLAG = re.compile(
    r"-server\.http-listen-address[=\s]+([^\s'\"]+)"
)


def _bind_is_loopback(addr: str) -> bool:
    addr = addr.strip().strip("'\"")
    if ":" in addr and addr.count(":") == 1:
        addr = addr.split(":", 1)[0]
    return addr in LOOPBACK


def scan(text: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    # File-level suppression: any line that is purely the suppression
    # comment (not just any occurrence — otherwise the README would
    # silence the rule).
    for raw in text.splitlines()[:5]:
        if raw.strip().startswith("#") and SUPPRESS_FILE.search(raw):
            return findings

    lines = text.splitlines()

    # Look for product-context evidence so we don't flag random YAML.
    ctx = "\n".join(lines).lower()
    has_product_ctx = any(
        kw in ctx
        for kw in (
            "mimir",
            "loki",
            "tempo",
            "cortex",
            "x-scope-orgid",
            "structuredconfig",
            "ruler_storage",
            "blocks_storage",
            "ingester",
            "querier",
            "distributor",
        )
    )

    cli_auth_disabled = False
    cli_bind = ""
    cli_auth_line = 0
    cli_bind_line = 0

    for i, raw in enumerate(lines, start=1):
        if SUPPRESS_LINE.search(raw):
            continue

        m_yaml = AUTH_DISABLED_RE.match(raw)
        if m_yaml and has_product_ctx:
            key = m_yaml.group(1)
            findings.append(
                (
                    i,
                    f"{key}=false disables tenant isolation; all requests collapse onto the 'fake' tenant",
                )
            )
            continue

        # Nested helm key (any indent) — only flag when surrounded by
        # mimir/loki/tempo context already (has_product_ctx) AND the
        # line is indented (so we don't double-count top-level hits).
        m_nested = HELM_NESTED_RE.match(raw)
        if m_nested and has_product_ctx and (len(raw) - len(raw.lstrip(" "))) > 0:
            findings.append(
                (
                    i,
                    f"{m_nested.group(1)}=false (nested) disables tenant isolation in helm values",
                )
            )

        if CLI_AUTH_FLAG.search(raw):
            cli_auth_disabled = True
            cli_auth_line = i
        m_bind = CLI_BIND_FLAG.search(raw)
        if m_bind:
            cli_bind = m_bind.group(1)
            cli_bind_line = i

    if cli_auth_disabled:
        if not cli_bind:
            findings.append(
                (
                    cli_auth_line,
                    "-auth.multitenancy-enabled=false with no explicit "
                    "-server.http-listen-address (defaults to 0.0.0.0)",
                )
            )
        elif not _bind_is_loopback(cli_bind):
            findings.append(
                (
                    cli_auth_line,
                    f"-auth.multitenancy-enabled=false while http listener bound to "
                    f"{cli_bind} (non-loopback) — see line {cli_bind_line}",
                )
            )

    # de-dup
    seen: set[Tuple[int, str]] = set()
    out: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


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

#!/usr/bin/env python3
"""Detect Cortex configurations from LLM output that effectively
disable multi-tenancy isolation.

Cortex (Grafana Labs' horizontally-scalable Prometheus storage) is
multi-tenant by default: every read/write is scoped by an
``X-Scope-OrgID`` header. The auth-stack is governed by:

    auth_enabled: true            # YAML
    -auth.enabled=true            # CLI

When ``auth_enabled`` is set to ``false`` (or ``-auth.enabled=false``
is passed), Cortex collapses *all* traffic into the synthetic single
tenant ``fake``. Any caller can read/write any series, and per-tenant
limits stop applying. LLMs frequently emit this shape because the
"getting started" single-binary doc disables auth to remove the need
for a header on curl examples.

This detector flags four orthogonal regressions that all collapse
multi-tenancy:

  1. ``auth_enabled: false`` at the top level of a Cortex YAML
     config.
  2. ``-auth.enabled=false`` on a ``cortex`` / ``cortex-all`` CLI
     invocation.
  3. ``no_auth_tenant: <something>`` (Mimir-style alias also accepted
     by recent Cortex distributions) set without an accompanying
     ``auth_enabled: true``.
  4. A Prometheus ``remote_write`` block that targets a Cortex
     ``/api/v1/push`` endpoint with no ``X-Scope-OrgID`` header in
     ``headers:`` — cleartext single-tenant push.

Suppression: a comment ``# cortex-single-tenant-allowed`` anywhere in
the file disables all rules (e.g. local dev fixtures).

CWE-862 (Missing Authorization) and CWE-639 (Authorization Bypass
Through User-Controlled Key) apply.

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

SUPPRESS = re.compile(r"#\s*cortex-single-tenant-allowed", re.IGNORECASE)

# ---- regexes ----
# top-level YAML key (zero indentation)
AUTH_ENABLED_FALSE_YAML = re.compile(
    r"^auth_enabled\s*:\s*(['\"]?)false\1\s*(?:#.*)?$",
    re.MULTILINE,
)
AUTH_ENABLED_TRUE_YAML = re.compile(
    r"^auth_enabled\s*:\s*(['\"]?)true\1\s*(?:#.*)?$",
    re.MULTILINE,
)

# CLI: -auth.enabled=false  OR  --auth.enabled=false  OR  -auth.enabled false
AUTH_FLAG_FALSE_CLI = re.compile(
    r"--?auth\.enabled[=\s]+(['\"]?)false\1\b"
)
AUTH_FLAG_TRUE_CLI = re.compile(
    r"--?auth\.enabled[=\s]+(['\"]?)true\1\b"
)

# no_auth_tenant: anonymous   (Mimir-aliased setting that some Cortex
# distributions accept; presence of a non-empty value with auth off is
# what we care about)
NO_AUTH_TENANT = re.compile(
    r"^\s*no_auth_tenant\s*:\s*(['\"]?)([A-Za-z0-9_\-]+)\1\s*(?:#.*)?$",
    re.MULTILINE,
)

# A cortex CLI invocation marker (any of these strongly implies cortex)
CORTEX_INVOCATION = re.compile(
    r"\b(cortex|cortex-all|cortex/cortex)\b"
)

# Prometheus remote_write block detection (very loose)
REMOTE_WRITE_HEAD = re.compile(r"^\s*remote_write\s*:\s*$", re.MULTILINE)
PUSH_URL = re.compile(
    r"url\s*:\s*['\"]?(https?://[^\s'\"]+/api/v1/push)['\"]?"
)


def _has_xscope_header(block: str) -> bool:
    return bool(re.search(r"X-Scope-OrgID", block, re.IGNORECASE))


def _scan_yaml_auth(text: str, lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for m in AUTH_ENABLED_FALSE_YAML.finditer(text):
        # compute 1-based line
        line_no = text.count("\n", 0, m.start()) + 1
        findings.append(
            (
                line_no,
                "auth_enabled: false collapses every request into the "
                "synthetic 'fake' tenant (multi-tenancy disabled)",
            )
        )
    return findings


def _scan_cli_auth(text: str, lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if not CORTEX_INVOCATION.search(text):
        # The CLI flag is generic; only flag when we see a cortex
        # invocation in the same blob.
        return findings
    for m in AUTH_FLAG_FALSE_CLI.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        findings.append(
            (
                line_no,
                "-auth.enabled=false on a cortex invocation disables "
                "tenant isolation (single-tenant 'fake')",
            )
        )
    return findings


def _scan_no_auth_tenant(text: str, lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    has_auth_true = bool(
        AUTH_ENABLED_TRUE_YAML.search(text) or AUTH_FLAG_TRUE_CLI.search(text)
    )
    if has_auth_true:
        return findings
    for m in NO_AUTH_TENANT.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        tenant = m.group(2)
        findings.append(
            (
                line_no,
                f"no_auth_tenant: {tenant} is set without auth_enabled: true "
                f"— every unauthenticated caller is mapped to that tenant",
            )
        )
    return findings


def _scan_remote_write(text: str, lines: List[str]) -> List[Tuple[int, str]]:
    """Walk every remote_write: block; for those that target an
    /api/v1/push endpoint, require an X-Scope-OrgID header somewhere
    inside the block."""
    findings: List[Tuple[int, str]] = []
    n = len(lines)
    for i, ln in enumerate(lines):
        if not REMOTE_WRITE_HEAD.match(ln):
            continue
        # determine the indentation of the remote_write key
        base_indent = len(ln) - len(ln.lstrip(" "))
        # collect block until we leave the indentation
        block_lines: List[str] = []
        block_start = i + 1
        j = i + 1
        while j < n:
            raw = lines[j]
            if raw.strip() == "":
                block_lines.append(raw)
                j += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if indent <= base_indent:
                break
            block_lines.append(raw)
            j += 1
        block = "\n".join(block_lines)
        m = PUSH_URL.search(block)
        if not m:
            continue
        url = m.group(1)
        # only flag if URL targets non-loopback
        host = url.split("//", 1)[1].split("/", 1)[0].split(":")[0]
        if host in {"127.0.0.1", "localhost", "::1"}:
            continue
        if _has_xscope_header(block):
            continue
        # find line of the url within the block for reporting
        url_line = block_start
        for k, bln in enumerate(block_lines):
            if url in bln:
                url_line = block_start + k
                break
        findings.append(
            (
                url_line,
                f"remote_write to {url} has no X-Scope-OrgID header "
                f"(single-tenant push; multi-tenancy not enforced)",
            )
        )
    return findings


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    lines = text.splitlines()
    findings: List[Tuple[int, str]] = []
    findings.extend(_scan_yaml_auth(text, lines))
    findings.extend(_scan_cli_auth(text, lines))
    findings.extend(_scan_no_auth_tenant(text, lines))
    findings.extend(_scan_remote_write(text, lines))
    # de-dup, preserve order
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

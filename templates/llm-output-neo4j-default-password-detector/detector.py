#!/usr/bin/env python3
"""Detect Neo4j configurations / client snippets that disable auth or
keep the install-default `neo4j / neo4j` credentials against a
non-loopback target.

Exits with the number of findings (0 = clean). Files containing the
suppression marker `neo4j-default-password-allowed` are skipped.
"""

from __future__ import annotations

import os
import re
import sys

SUPPRESS_MARK = "neo4j-default-password-allowed"

# neo4j.conf: dbms.security.auth_enabled=false
AUTH_DISABLED_CONF = re.compile(
    r"""^\s*dbms\.security\.auth_enabled\s*=\s*(false|no|off|0)\s*(?:#.*)?$""",
    re.IGNORECASE | re.MULTILINE,
)

# NEO4J_AUTH=none
ENV_AUTH_NONE = re.compile(
    r"""(?:^|[\s;])NEO4J_AUTH\s*=\s*['"]?none['"]?\b""",
    re.IGNORECASE,
)

# NEO4J_AUTH=neo4j/neo4j  (or with leading "neo4j_auth:" yaml form)
ENV_AUTH_DEFAULT = re.compile(
    r"""NEO4J_AUTH\s*[:=]\s*['"]?neo4j\s*/\s*neo4j['"]?""",
    re.IGNORECASE,
)

# Driver code: GraphDatabase.driver("bolt://host:7687", auth=("neo4j", "neo4j"))
DRIVER_CALL = re.compile(
    r"""GraphDatabase\.driver\(\s*['"]([^'"]+)['"]\s*,\s*auth\s*=\s*\(\s*['"]neo4j['"]\s*,\s*['"]neo4j['"]\s*\)""",
    re.IGNORECASE,
)

# cypher-shell -u neo4j -p neo4j -a bolt://host:7687
CYPHER_SHELL = re.compile(
    r"""cypher-shell\b[^\n]*?\s-u\s+neo4j\b[^\n]*?\s-p\s+neo4j\b""",
    re.IGNORECASE,
)
CYPHER_SHELL_HOST = re.compile(
    r"""-a\s+['"]?(?:bolt|neo4j)(?:\+s|\+ssc)?://([^/\s'"]+)""",
    re.IGNORECASE,
)

LOOPBACK_HOST_RE = re.compile(
    r"""^(127\.\d+\.\d+\.\d+|::1|localhost)$""", re.IGNORECASE
)


def _is_loopback_host(host: str) -> bool:
    h = host.split(":", 1)[0].strip("[]")
    return bool(LOOPBACK_HOST_RE.match(h))


def _uri_host(uri: str) -> str | None:
    m = re.match(r"""[a-z0-9+]+://(?:[^@/]*@)?([^/\s]+)""", uri, re.IGNORECASE)
    return m.group(1) if m else None


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    findings: list[str] = []

    if AUTH_DISABLED_CONF.search(text):
        findings.append(
            f"{path}: dbms.security.auth_enabled=false — Neo4j is "
            f"reachable without any credential check"
        )
    if ENV_AUTH_NONE.search(text):
        findings.append(
            f"{path}: NEO4J_AUTH=none — container starts with auth "
            f"disabled"
        )
    if ENV_AUTH_DEFAULT.search(text):
        findings.append(
            f"{path}: NEO4J_AUTH pinned to default neo4j/neo4j — "
            f"forced password rotation is bypassed"
        )

    for m in DRIVER_CALL.finditer(text):
        uri = m.group(1)
        host = _uri_host(uri) or ""
        if not _is_loopback_host(host):
            findings.append(
                f"{path}: GraphDatabase.driver uses neo4j/neo4j against "
                f"non-loopback host '{host}'"
            )

    if CYPHER_SHELL.search(text):
        host_m = CYPHER_SHELL_HOST.search(text)
        host = host_m.group(1) if host_m else ""
        if not host or not _is_loopback_host(host):
            findings.append(
                f"{path}: cypher-shell invoked with neo4j/neo4j against "
                f"host '{host or '(unspecified)'}'"
            )

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [file ...]", file=sys.stderr)
        return 2
    files: list[str] = []
    for arg in argv[1:]:
        if os.path.isdir(arg):
            for root, _, names in os.walk(arg):
                for name in names:
                    files.append(os.path.join(root, name))
        else:
            files.append(arg)

    total = 0
    for f in files:
        for finding in scan_file(f):
            print(finding)
            total += 1
    return total


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

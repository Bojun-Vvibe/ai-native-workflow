#!/usr/bin/env python3
"""Detect Kibana configurations that disable the security plugin or
keep the install-default `kibana / changeme` credential pair.

Exits with the number of findings (0 = clean). Files containing the
suppression marker `kibana-no-auth-allowed` are skipped.
"""

from __future__ import annotations

import os
import re
import sys

SUPPRESS_MARK = "kibana-no-auth-allowed"

# kibana.yml: `xpack.security.enabled: false`
YAML_SECURITY_DISABLED = re.compile(
    r"""^\s*xpack\.security\.enabled\s*:\s*(false|no|off|0)\s*(?:#.*)?$""",
    re.IGNORECASE | re.MULTILINE,
)

# Env var form: XPACK_SECURITY_ENABLED=false
ENV_SECURITY_DISABLED = re.compile(
    r"""(?:^|[\s;])XPACK_SECURITY_ENABLED\s*=\s*['"]?(false|no|off|0)['"]?\b""",
    re.IGNORECASE,
)

# CLI flag: --xpack.security.enabled=false  or  --xpack.security.enabled false
CLI_SECURITY_DISABLED = re.compile(
    r"""--xpack\.security\.enabled[\s=]+['"]?(false|no|off|0)['"]?\b""",
    re.IGNORECASE,
)

# Anonymous auth provider with no credentials block.
ANON_PROVIDER = re.compile(
    r"""xpack\.security\.authc\.providers\s*:\s*(?:\[[^\]]*anonymous[^\]]*\]|.*\n(?:\s+.*\n)*?\s*anonymous\s*:)""",
    re.IGNORECASE,
)

# Default install credentials still in use.
DEFAULT_PASSWORD = re.compile(
    r"""elasticsearch\.password\s*[:=]\s*['"]?changeme['"]?""",
    re.IGNORECASE,
)


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    findings: list[str] = []

    if YAML_SECURITY_DISABLED.search(text):
        findings.append(
            f"{path}: kibana.yml sets xpack.security.enabled: false — "
            f"UI is reachable without authentication"
        )
    if ENV_SECURITY_DISABLED.search(text):
        findings.append(
            f"{path}: XPACK_SECURITY_ENABLED=false in env — "
            f"UI is reachable without authentication"
        )
    if CLI_SECURITY_DISABLED.search(text):
        findings.append(
            f"{path}: --xpack.security.enabled=false on command line — "
            f"UI is reachable without authentication"
        )
    if ANON_PROVIDER.search(text):
        findings.append(
            f"{path}: anonymous authc provider configured — "
            f"unauthenticated callers are accepted"
        )
    if DEFAULT_PASSWORD.search(text):
        findings.append(
            f"{path}: elasticsearch.password is install-default 'changeme' — "
            f"rotate before exposing the host"
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

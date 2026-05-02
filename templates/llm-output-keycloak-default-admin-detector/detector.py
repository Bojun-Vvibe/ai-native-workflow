#!/usr/bin/env python3
"""Detect Keycloak bootstrap configurations that ship the
well-known default admin credential ``admin/admin`` (or trivial
variants) into a deployable artifact — Dockerfile, docker-compose,
Kubernetes manifest, Helm values, systemd EnvironmentFile, or shell
script that exports ``KEYCLOAK_ADMIN`` / ``KEYCLOAK_ADMIN_PASSWORD``
(or the legacy ``KC_BOOTSTRAP_ADMIN_*`` / ``KEYCLOAK_USER`` /
``KEYCLOAK_PASSWORD`` pairs).

Background. Keycloak's quay.io image creates the initial realm admin
from two environment variables at first boot. Every "getting started"
blog post on the planet sets them to ``admin`` / ``admin``, and LLM
output tends to copy that verbatim into production-shaped manifests.
Once the realm is created, that account survives unless an operator
manually rotates it; quay images expose the admin console on
``/admin`` over the same listener as user-facing flows, so a leaked
default credential is a full identity-provider takeover.

What's checked (per file):
  - ``KEYCLOAK_ADMIN`` / ``KEYCLOAK_ADMIN_PASSWORD`` set to a value in
    the trivial set ``{admin, administrator, keycloak, password,
    changeme, root, 12345, 123456}``.
  - Same for the legacy ``KEYCLOAK_USER`` / ``KEYCLOAK_PASSWORD`` pair
    (Keycloak < 17 / Wildfly distribution).
  - Same for the modern ``KC_BOOTSTRAP_ADMIN_USERNAME`` /
    ``KC_BOOTSTRAP_ADMIN_PASSWORD`` pair (Keycloak 26+).
  - ``--bootstrap-admin-username`` / ``--bootstrap-admin-password``
    CLI flags.
  - Detects in ``ENV`` / ``ARG`` (Dockerfile), ``environment:`` map
    (compose), ``env:`` list (k8s), ``KEY=VALUE`` (.env / systemd
    EnvironmentFile / shell ``export`` lines), and YAML
    ``data:`` / ``stringData:`` of a Secret.

Findings are reported per-line.

CWE refs:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements

False-positive surface:
  - The literal value ``$(...)`` / ``${...}`` / ``<<...>>`` is treated
    as an unresolved placeholder and not flagged.
  - A file containing the marker ``# keycloak-default-admin-allowed``
    is suppressed (e.g. ephemeral test fixtures).
  - Username matches alone are not enough; a password match (or a
    paired username+password where both are trivial) is required to
    fire.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*keycloak-default-admin-allowed")

TRIVIAL = {
    "admin",
    "administrator",
    "keycloak",
    "password",
    "passw0rd",
    "changeme",
    "change-me",
    "root",
    "12345",
    "123456",
    "qwerty",
    "letmein",
    "secret",
    "default",
}

# Variable names we treat as "the admin username".
USER_KEYS = {
    "KEYCLOAK_ADMIN",
    "KEYCLOAK_USER",
    "KC_BOOTSTRAP_ADMIN_USERNAME",
}
# Variable names we treat as "the admin password".
PASS_KEYS = {
    "KEYCLOAK_ADMIN_PASSWORD",
    "KEYCLOAK_PASSWORD",
    "KC_BOOTSTRAP_ADMIN_PASSWORD",
}

# Matches `KEY=value`, `KEY: value`, `KEY value` (Dockerfile ENV/ARG),
# and YAML list entries like `- name: KEY` followed by `value: ...`.
KV_RE = re.compile(
    r"""
    (?:^|[\s,;])                                         # boundary
    (?P<key>KEYCLOAK_ADMIN_PASSWORD|KEYCLOAK_ADMIN
        |KEYCLOAK_PASSWORD|KEYCLOAK_USER
        |KC_BOOTSTRAP_ADMIN_PASSWORD
        |KC_BOOTSTRAP_ADMIN_USERNAME)
    \s*[:=\s]\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s,;]+)
    """,
    re.VERBOSE,
)

# CLI flags: --bootstrap-admin-username admin --bootstrap-admin-password admin
CLI_RE = re.compile(
    r"--bootstrap-admin-(?P<which>username|password)(?:\s+|=)(?P<val>[^\s\"']+)",
    re.IGNORECASE,
)

# YAML k8s-style env list entry split across lines:
#   - name: KEYCLOAK_ADMIN_PASSWORD
#     value: admin
K8S_NAME_RE = re.compile(
    r"^\s*-\s*name\s*:\s*(?P<key>[A-Z_][A-Z0-9_]*)\s*$"
)
K8S_VALUE_RE = re.compile(
    r"^\s*value\s*:\s*(?P<val>\"[^\"]*\"|'[^']*'|\S.*?)\s*$"
)


def _strip(value: str) -> str:
    v = value.strip()
    if (v.startswith('"') and v.endswith('"')) or (
        v.startswith("'") and v.endswith("'")
    ):
        v = v[1:-1]
    return v


def _is_placeholder(value: str) -> bool:
    v = value.strip()
    if not v:
        return True
    # ${VAR}, $(...), <<TOKEN>>, {{TEMPLATE}}, %ENV%
    return any(
        marker in v
        for marker in ("${", "$(", "<<", "{{", "%(", "%ENV%")
    )


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()

    # First pass: collect inline KV findings + CLI flags.
    inline_pass: Dict[int, Tuple[str, str]] = {}
    for i, raw in enumerate(lines, start=1):
        for m in KV_RE.finditer(raw):
            key = m.group("key")
            val = _strip(m.group("val"))
            if _is_placeholder(val):
                continue
            inline_pass[i] = (key, val)
            if key in PASS_KEYS and val.lower() in TRIVIAL:
                findings.append((
                    i,
                    f"{key} set to trivial/default value '{val}' — Keycloak "
                    f"bootstrap admin password must be unique per environment",
                ))
            elif key in USER_KEYS and val.lower() in TRIVIAL:
                # Username alone is borderline; record it for pairing.
                pass

        for m in CLI_RE.finditer(raw):
            which = m.group("which").lower()
            val = m.group("val")
            if _is_placeholder(val):
                continue
            if which == "password" and val.lower() in TRIVIAL:
                findings.append((
                    i,
                    f"--bootstrap-admin-password '{val}' is a trivial default "
                    f"credential",
                ))

    # Second pass: split-line k8s-style env entries.
    for i, raw in enumerate(lines, start=1):
        m = K8S_NAME_RE.match(raw)
        if not m:
            continue
        key = m.group("key")
        if key not in PASS_KEYS and key not in USER_KEYS:
            continue
        # Look ahead up to 4 lines for `value:`.
        for j in range(i, min(i + 4, len(lines))):
            vm = K8S_VALUE_RE.match(lines[j])
            if vm:
                val = _strip(vm.group("val"))
                if _is_placeholder(val):
                    break
                if key in PASS_KEYS and val.lower() in TRIVIAL:
                    findings.append((
                        j + 1,
                        f"{key} set to trivial/default value '{val}' "
                        f"(k8s env entry)",
                    ))
                break

    # Pair-trivial detection: if both a USER_KEY and a PASS_KEY appear
    # in the same file, both with trivial values, fire even if the
    # password value alone wouldn't have been flagged (it always will,
    # but this also surfaces the username for the report).
    seen_users = {
        v.lower() for (k, v) in inline_pass.values() if k in USER_KEYS
    }
    if "admin" in seen_users:
        # Already covered by password finding; no extra noise.
        pass

    findings.sort(key=lambda x: x[0])
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in (
                "*.yaml",
                "*.yml",
                "*.env",
                "*.sh",
                "Dockerfile",
                "docker-compose*",
                "*.conf",
            ):
                targets.extend(sorted(path.rglob(ext)))
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

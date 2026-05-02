#!/usr/bin/env python3
"""Detect Zabbix bootstrap configurations that ship the well-known
default Super Admin credential ``Admin`` / ``zabbix`` (or trivial
variants) into a deployable artifact.

The Zabbix web frontend hard-codes a factory account ``Admin`` (capital
A) whose initial password is the literal string ``zabbix``. The
documented post-install step is to rotate it; LLM-generated manifests
routinely skip that step and copy the documented bootstrap value
verbatim into production-shaped artifacts (docker-compose, Helm
values, Kubernetes Secrets, ``.env`` files, JSON-RPC seed scripts).
The frontend is reachable on the same listener that serves
dashboards (``/zabbix/index.php``); a leaked default credential is a
full monitoring-system takeover.

What's checked (per file):
  - ``ZBX_SERVER_USER`` / ``ZBX_SERVER_PASSWORD``
  - ``ZABBIX_USER`` / ``ZABBIX_PASSWORD``
  - ``PHP_ZBX_USER`` / ``PHP_ZBX_PASSWORD``
  - ``ZBX_FRONTEND_USER`` / ``ZBX_FRONTEND_PASSWORD``
  - ``--zabbix-user`` / ``--zabbix-password`` CLI flags
  - JSON literals containing ``"user": "Admin"`` AND
    ``"password": "<trivial>"`` (typical user.login bootstrap script)
  - Detected in ``ENV`` / ``ARG`` (Dockerfile), ``environment:``
    map (compose), ``env:`` list (k8s), ``KEY=VALUE`` (.env / systemd
    EnvironmentFile / shell ``export`` lines), and YAML
    ``data:`` / ``stringData:`` of a Secret.

CWE refs:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements

False-positive surface:
  - The literal value ``$(...)`` / ``${...}`` / ``<<...>>`` /
    ``{{...}}`` is treated as an unresolved placeholder and skipped.
  - A file containing the marker ``# zabbix-default-admin-allowed``
    is suppressed.
  - A trivial username alone is not enough; a trivial password must
    appear for the detector to fire.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*zabbix-default-admin-allowed")

TRIVIAL = {
    "zabbix",
    "admin",
    "administrator",
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

USER_KEYS = {
    "ZBX_SERVER_USER",
    "ZABBIX_USER",
    "PHP_ZBX_USER",
    "ZBX_FRONTEND_USER",
}
PASS_KEYS = {
    "ZBX_SERVER_PASSWORD",
    "ZABBIX_PASSWORD",
    "PHP_ZBX_PASSWORD",
    "ZBX_FRONTEND_PASSWORD",
}

KV_RE = re.compile(
    r"""
    (?:^|[\s,;])
    (?P<key>ZBX_SERVER_PASSWORD|ZBX_SERVER_USER
        |ZABBIX_PASSWORD|ZABBIX_USER
        |PHP_ZBX_PASSWORD|PHP_ZBX_USER
        |ZBX_FRONTEND_PASSWORD|ZBX_FRONTEND_USER)
    \s*[:=\s]\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s,;]+)
    """,
    re.VERBOSE,
)

CLI_RE = re.compile(
    r"--zabbix-(?P<which>user|password)(?:\s+|=)(?P<val>[^\s\"']+)",
    re.IGNORECASE,
)

K8S_NAME_RE = re.compile(
    r"^\s*-\s*name\s*:\s*(?P<key>[A-Z_][A-Z0-9_]*)\s*$"
)
K8S_VALUE_RE = re.compile(
    r"^\s*value\s*:\s*(?P<val>\"[^\"]*\"|'[^']*'|\S.*?)\s*$"
)

# JSON-RPC user.login bootstrap pattern.
JSON_USER_RE = re.compile(r'"user"\s*:\s*"(?P<u>[^"]+)"')
JSON_PASS_RE = re.compile(r'"password"\s*:\s*"(?P<p>[^"]+)"')


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
    return any(
        marker in v
        for marker in ("${", "$(", "<<", "{{", "%(", "%ENV%")
    )


def _scan_inline_kv(lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(lines, start=1):
        for m in KV_RE.finditer(raw):
            key = m.group("key")
            val = _strip(m.group("val"))
            if _is_placeholder(val):
                continue
            if key in PASS_KEYS and val.lower() in TRIVIAL:
                findings.append((
                    i,
                    f"{key} set to trivial/default value '{val}' — "
                    f"Zabbix Super Admin password must be unique per "
                    f"environment",
                ))
        for m in CLI_RE.finditer(raw):
            which = m.group("which").lower()
            val = m.group("val")
            if _is_placeholder(val):
                continue
            if which == "password" and val.lower() in TRIVIAL:
                findings.append((
                    i,
                    f"--zabbix-password '{val}' is a trivial default "
                    f"credential",
                ))
    return findings


def _scan_k8s(lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(lines, start=1):
        m = K8S_NAME_RE.match(raw)
        if not m:
            continue
        key = m.group("key")
        if key not in PASS_KEYS:
            continue
        for j in range(i, min(i + 4, len(lines))):
            vm = K8S_VALUE_RE.match(lines[j])
            if vm:
                val = _strip(vm.group("val"))
                if _is_placeholder(val):
                    break
                if val.lower() in TRIVIAL:
                    findings.append((
                        j + 1,
                        f"{key} set to trivial/default value '{val}' "
                        f"(k8s env entry)",
                    ))
                break
    return findings


def _scan_json_login(source: str, lines: List[str]) -> List[Tuple[int, str]]:
    """Catch user.login JSON-RPC seed payloads with trivial creds."""
    findings: List[Tuple[int, str]] = []
    if "user.login" not in source:
        return findings
    user_hits = [
        (i + 1, m.group("u"))
        for i, raw in enumerate(lines)
        for m in [JSON_USER_RE.search(raw)]
        if m
    ]
    pass_hits = [
        (i + 1, m.group("p"))
        for i, raw in enumerate(lines)
        for m in [JSON_PASS_RE.search(raw)]
        if m
    ]
    if not user_hits or not pass_hits:
        return findings
    # If any user is "Admin"/"admin" AND any password is trivial,
    # report against the password line.
    triv_user = any(u.lower() in {"admin", "administrator"} for _, u in user_hits)
    if not triv_user:
        return findings
    for line, pwd in pass_hits:
        if _is_placeholder(pwd):
            continue
        if pwd.lower() in TRIVIAL:
            findings.append((
                line,
                f"user.login JSON-RPC payload uses trivial Zabbix "
                f"password '{pwd}' for the Admin account",
            ))
    return findings


def scan(source: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    lines = source.splitlines()
    findings: List[Tuple[int, str]] = []
    findings.extend(_scan_inline_kv(lines))
    findings.extend(_scan_k8s(lines))
    findings.extend(_scan_json_login(source, lines))
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
                "*.json",
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

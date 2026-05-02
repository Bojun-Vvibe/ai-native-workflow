#!/usr/bin/env python3
"""Detect Rundeck bootstrap configurations that ship the well-known
default admin credential ``admin:admin`` (or trivial variants) into a
deployable artifact.

The official Rundeck distribution ships a JAAS file-based realm at
``server/config/realm.properties`` with a documented bootstrap entry
``admin: admin, user, admin`` (cleartext password ``admin``, two
roles). The official Docker image exposes ``RUNDECK_ADMIN_PASSWORD``
which seeds that same realm. LLM-generated manifests routinely copy
the documented bootstrap value verbatim into production-shaped
artifacts (Dockerfile, docker-compose, Kubernetes Secrets, Helm
values, seed shell scripts that hit the API with ``-u admin:admin``).
The Rundeck UI / API are reachable on the same listener that runs job
executions; a leaked default credential is a remote command-execution
surface across every managed node.

What's checked (per file):
  - ``RUNDECK_ADMIN_PASSWORD`` / ``RD_ADMIN_PASSWORD`` env values.
  - ``realm.properties`` JAAS entries shaped
    ``<user>: <password>, <role>[, <role>...]`` where the password
    cleartext is in the trivial set. Hashed values
    (``MD5:``, ``CRYPT:``, ``OBF:`` prefix) are skipped.
  - ``framework.server.password=<trivial>`` and
    ``rundeck.api.tokens.duration.max`` is NOT touched (only the
    password line is flagged).
  - shell ``curl -u admin:<trivial>`` / ``--user admin:<trivial>``
    invocations.
  - YAML ``env:`` list k8s-style entries (split-line
    ``- name:`` / ``  value:``).

CWE refs:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements

False-positive surface:
  - Values resolving to ``${...}`` / ``$(...)`` / ``<<...>>`` /
    ``{{...}}`` / ``%ENV%`` are unresolved placeholders, not flagged.
  - Files containing the marker ``# rundeck-default-admin-allowed``
    are suppressed.
  - Hashed JAAS passwords are skipped.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*rundeck-default-admin-allowed")

TRIVIAL = {
    "admin",
    "administrator",
    "rundeck",
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

PASS_KEYS = {
    "RUNDECK_ADMIN_PASSWORD",
    "RD_ADMIN_PASSWORD",
}

KV_RE = re.compile(
    r"""
    (?:^|[\s,;])
    (?P<key>RUNDECK_ADMIN_PASSWORD|RD_ADMIN_PASSWORD)
    \s*[:=\s]\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s,;]+)
    """,
    re.VERBOSE,
)

# realm.properties JAAS entry: `user: password, role1, role2`
JAAS_RE = re.compile(
    r"""
    ^\s*
    (?P<user>[A-Za-z_][A-Za-z0-9_.\-]*)
    \s*:\s*
    (?P<pwd>[^,\s][^,]*?)
    \s*,\s*
    (?P<roles>[A-Za-z][\w,\s]*?)
    \s*$
    """,
    re.VERBOSE,
)

# framework.properties / rundeck-config.properties
FRAMEWORK_PASS_RE = re.compile(
    r"^\s*framework\.server\.password\s*=\s*(?P<val>\S.*?)\s*$"
)

# curl -u admin:admin / --user admin:admin
CURL_AUTH_RE = re.compile(
    r"(?:--user|-u)\s+(?P<user>[A-Za-z0-9_.\-]+):(?P<pwd>[^\s\"']+)"
)

# k8s env split-line
K8S_NAME_RE = re.compile(
    r"^\s*-\s*name\s*:\s*(?P<key>[A-Z_][A-Z0-9_]*)\s*$"
)
K8S_VALUE_RE = re.compile(
    r"^\s*value\s*:\s*(?P<val>\"[^\"]*\"|'[^']*'|\S.*?)\s*$"
)

HASH_PREFIXES = ("MD5:", "CRYPT:", "OBF:")


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


def _is_hashed(value: str) -> bool:
    v = value.strip().upper()
    return any(v.startswith(p) for p in HASH_PREFIXES)


def _scan_env_kv(lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(lines, start=1):
        for m in KV_RE.finditer(raw):
            key = m.group("key")
            val = _strip(m.group("val"))
            if _is_placeholder(val) or _is_hashed(val):
                continue
            if val.lower() in TRIVIAL:
                findings.append((
                    i,
                    f"{key} set to trivial/default value '{val}' — "
                    f"Rundeck bootstrap admin password must be unique "
                    f"per environment",
                ))
    return findings


def _scan_jaas(path: Path, lines: List[str]) -> List[Tuple[int, str]]:
    """Only fire on files that look like a JAAS realm.properties.

    Heuristic: file basename mentions ``realm`` and ``.properties``,
    OR the file contains at least one entry with the role ``admin``
    or ``user`` after a colon-separated password.
    """
    findings: List[Tuple[int, str]] = []
    name = path.name.lower()
    looks_like_realm = (
        "realm" in name and name.endswith(".properties")
    ) or any(
        re.search(r":\s*\S+\s*,\s*(?:user|admin|architect)\b", line)
        for line in lines
    )
    if not looks_like_realm:
        return findings

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = JAAS_RE.match(raw)
        if not m:
            continue
        user = m.group("user")
        pwd = m.group("pwd").strip()
        roles = m.group("roles")
        # Roles must look like JAAS roles to be sure this isn't
        # a coincidental `key: value, foo` line.
        role_tokens = [r.strip() for r in roles.split(",") if r.strip()]
        if not role_tokens:
            continue
        if not all(re.match(r"^[A-Za-z][\w\-]*$", r) for r in role_tokens):
            continue
        if _is_placeholder(pwd) or _is_hashed(pwd):
            continue
        if pwd.lower() in TRIVIAL:
            findings.append((
                i,
                f"realm.properties user '{user}' uses trivial password "
                f"'{pwd}' — Rundeck bootstrap admin must be rotated",
            ))
    return findings


def _scan_framework(lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(lines, start=1):
        m = FRAMEWORK_PASS_RE.match(raw)
        if not m:
            continue
        val = _strip(m.group("val"))
        if _is_placeholder(val) or _is_hashed(val):
            continue
        if val.lower() in TRIVIAL:
            findings.append((
                i,
                f"framework.server.password set to trivial/default "
                f"value '{val}'",
            ))
    return findings


def _scan_curl(lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(lines, start=1):
        for m in CURL_AUTH_RE.finditer(raw):
            user = m.group("user").lower()
            pwd = m.group("pwd")
            if _is_placeholder(pwd):
                continue
            if user in {"admin", "administrator"} and pwd.lower() in TRIVIAL:
                findings.append((
                    i,
                    f"curl invocation uses trivial Rundeck admin "
                    f"credential 'admin:{pwd}'",
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
                if _is_placeholder(val) or _is_hashed(val):
                    break
                if val.lower() in TRIVIAL:
                    findings.append((
                        j + 1,
                        f"{key} set to trivial/default value '{val}' "
                        f"(k8s env entry)",
                    ))
                break
    return findings


def scan(source: str, path: Path) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    lines = source.splitlines()
    findings: List[Tuple[int, str]] = []
    findings.extend(_scan_env_kv(lines))
    findings.extend(_scan_jaas(path, lines))
    findings.extend(_scan_framework(lines))
    findings.extend(_scan_curl(lines))
    findings.extend(_scan_k8s(lines))
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
                "*.properties",
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
        hits = scan(source, f)
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

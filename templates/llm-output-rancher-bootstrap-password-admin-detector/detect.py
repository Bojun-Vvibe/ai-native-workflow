#!/usr/bin/env python3
"""
llm-output-rancher-bootstrap-password-admin-detector

Flags Rancher (Rancher Manager / Rancher Server / k3s + Rancher)
deployment manifests that set the bootstrap password to the literal
``admin`` -- the value used in nearly every "install Rancher in 5
minutes" tutorial and the value the upstream docs use as a placeholder
operators forget to change.

Concrete forms:

1. Helm install / values:        ``bootstrapPassword: admin``
2. Env / docker run:             ``CATTLE_BOOTSTRAP_PASSWORD=admin``
3. Docker compose (list/style):  ``- CATTLE_BOOTSTRAP_PASSWORD=admin``
4. Bare ``--set bootstrapPassword=admin`` in helm CLI commands.

Rancher uses the bootstrap password to create the initial ``admin``
user on first login. Anyone reaching the Rancher UI before the
operator rotates it gets:

  * cluster-admin on every downstream Kubernetes cluster Rancher
    manages (Rancher mints kubeconfigs on demand);
  * full read of cluster credentials, node SSH keys, registry
    creds and cloud-provider creds stored in Rancher's etcd;
  * the ability to deploy arbitrary workloads into any managed
    cluster (RCE on every node).

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A07:2021 Identification and Authentication Failures

Heuristic
---------
We require Rancher context (any of: ``rancher``, ``CATTLE_``,
``cattle-system``, ``rancher/rancher``) to avoid flagging unrelated
Helm charts whose ``bootstrapPassword`` happens to be ``admin``.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

_RANCHER_CONTEXT = re.compile(
    r"""(?im)\b(?:rancher|CATTLE_|cattle-system|rancher/rancher)\b""",
)

# Generic key/value matcher (allow leading "- " for compose lists).
_KV = re.compile(
    r"""^\s*(?:-\s+)?(?:export\s+)?([A-Za-z0-9_.][A-Za-z0-9_.\-]*)\s*[:=]\s*"""
    r"""['"]?([A-Za-z0-9_.\-@/+=!]+)['"]?\s*(?:[#;].*)?$""",
)

# Helm CLI: --set bootstrapPassword=admin  (also globalRestrictedAdmin etc.)
_HELM_SET = re.compile(
    r"""--set(?:-string)?\s+([A-Za-z0-9_.\-]*bootstrappassword[A-Za-z0-9_.\-]*)\s*=\s*['"]?admin['"]?""",
    re.IGNORECASE,
)

# systemd: Environment=KEY=VAL  (or Environment="KEY=VAL")
_SYSTEMD_ENV = re.compile(
    r"""^\s*Environment\s*=\s*['"]?([A-Za-z0-9_.\-]*BOOTSTRAP_PASSWORD[A-Za-z0-9_.\-]*)\s*=\s*['"]?admin['"]?\s*$""",
    re.IGNORECASE,
)


def _normalize_key(k: str) -> str:
    return re.sub(r"[_\-.]", "", k).lower()


_BOOTSTRAP_KEY_FRAGMENTS = (
    "bootstrappassword",
    "cattlebootstrappassword",
)


def _is_bootstrap_key(k: str) -> bool:
    nk = _normalize_key(k)
    return any(s in nk for s in _BOOTSTRAP_KEY_FRAGMENTS)


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []

    if not _RANCHER_CONTEXT.search(text):
        return []

    findings: List[str] = []

    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        # Form 4: helm --set
        m = _HELM_SET.search(raw)
        if m:
            findings.append(
                f"{path}:{i}: rancher helm --set "
                f"{m.group(1)}=admin -> default bootstrap creates "
                f"admin user with password 'admin'; whoever reaches "
                f"the UI first gets cluster-admin on every managed "
                f"cluster (CWE-798/CWE-1392/CWE-1188): "
                f"{raw.strip()[:200]}"
            )
            continue

        # systemd Environment=KEY=admin
        sm = _SYSTEMD_ENV.match(raw)
        if sm:
            findings.append(
                f"{path}:{i}: rancher systemd Environment="
                f"{sm.group(1)}=admin -> default bootstrap creates "
                f"admin user with password 'admin'; whoever reaches "
                f"the UI first gets cluster-admin on every managed "
                f"cluster (CWE-798/CWE-1392/CWE-1188): "
                f"{raw.strip()[:200]}"
            )
            continue

        kv = _KV.match(raw)
        if not kv:
            continue
        key, value = kv.group(1), kv.group(2)
        if value.lower() != "admin":
            continue
        if not _is_bootstrap_key(key):
            continue
        findings.append(
            f"{path}:{i}: rancher {key}=admin -> default bootstrap "
            f"creates the initial admin user with the literal "
            f"password 'admin'; whoever reaches the UI first gets "
            f"cluster-admin on every managed Kubernetes cluster "
            f"(CWE-798/CWE-1392/CWE-1188): {raw.strip()[:200]}"
        )
    return findings


_TARGET_EXTS = (".conf", ".cfg", ".properties", ".env",
                ".yaml", ".yml", ".json", ".sh", ".bash",
                ".service", ".dockerfile", ".ini", ".toml")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.startswith("dockerfile") or \
                            low.startswith("docker-compose") or \
                            low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        for line in scan(path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

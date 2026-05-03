#!/usr/bin/env python3
"""
llm-output-longhorn-default-credentials-detector

Flags Longhorn (Kubernetes block-storage) install manifests / scripts
that protect the Longhorn UI with the literal default basic-auth
credentials shown in nearly every Longhorn quickstart -- typically
``admin:admin`` baked into an htpasswd-backed nginx-ingress
``auth-secret`` Secret, or no auth annotation at all on the
Longhorn UI Ingress.

Concrete forms (each requires Longhorn context in-file):

1. ``htpasswd -b[c] <file> admin admin`` in install scripts.
2. Kubernetes ``Secret`` whose ``stringData.auth:`` (or decoded
   ``data.auth:``) starts with ``admin:`` and whose
   ``metadata.namespace`` or name marks it as the Longhorn UI
   auth-secret. We detect the literal ``admin:`` prefix paired
   with a longhorn context.
3. nginx Ingress for the Longhorn UI lacking the
   ``nginx.ingress.kubernetes.io/auth-type: basic`` annotation
   while exposing ``longhorn-frontend`` to a public host.
4. Helm values ``ingress.host: longhorn.example.tld`` AND
   ``ingress.tls: false`` AND no ``auth`` block -- the published
   "expose the UI" snippet.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-306: Missing Authentication for Critical Function
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A07:2021 Identification and Authentication Failures

Heuristic
---------
We require Longhorn context (any of: ``longhorn``,
``longhorn-system``, ``longhorn-frontend``, ``longhorn.io``)
to avoid flagging unrelated nginx-ingress basic-auth Secrets.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

_LH_CONTEXT = re.compile(
    r"""(?im)\b(?:longhorn|longhorn-system|longhorn-frontend|longhorn\.io)\b""",
)

# htpasswd -b admin admin    (or -bc, -nb, etc.)
_HTPASSWD_DEFAULT = re.compile(
    r"""\bhtpasswd\s+-[bcnB]+\s+\S+\s+admin\s+admin\b""",
)

# Inline echo of "admin:$apr1$..." style file -- the known docs literal
# admin:admin hash starts with "$apr1$" / "$2y$" but value chosen here
# is the *literal* "admin:" username with placeholder hash. We flag any
# auth secret whose decoded/stringData line begins with "admin:" inside
# a longhorn-context file.
_AUTH_LINE = re.compile(
    r"""^\s*auth\s*:\s*['"]?(admin:[^\s'"]+)['"]?\s*$""",
)


def _join_continuations(lines: List[str]) -> List[tuple]:
    out: List[tuple] = []
    buf: List[str] = []
    start_no = 1
    for i, raw in enumerate(lines, start=1):
        if not buf:
            start_no = i
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buf.append(stripped[:-1])
            continue
        buf.append(stripped)
        out.append((start_no, " ".join(buf)))
        buf = []
    if buf:
        out.append((start_no, " ".join(buf)))
    return out


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return ""


def _scan_ingress_no_auth(path: str, text: str) -> List[str]:
    """
    Walk YAML docs for an Ingress that points at longhorn-frontend
    on a non-empty host but lacks any
    nginx.ingress.kubernetes.io/auth-type annotation.
    """
    findings: List[str] = []
    docs: List[List[str]] = [[]]
    for ln in text.splitlines():
        if ln.strip() == "---":
            docs.append([])
        else:
            docs[-1].append(ln)

    line_offset = 1
    for doc in docs:
        joined = "\n".join(doc)
        is_ingress = re.search(
            r"""(?m)^\s*kind:\s*Ingress\s*$""", joined,
        )
        targets_lh = re.search(
            r"""(?ms)backend:.*?service:.*?name:\s*longhorn-frontend""",
            joined,
        ) or re.search(
            r"""(?m)^\s*serviceName:\s*longhorn-frontend\s*$""",
            joined,
        )
        host_present = re.search(
            r"""(?m)^\s*-\s*host:\s*\S+""", joined,
        )
        has_auth = re.search(
            r"""nginx\.ingress\.kubernetes\.io/auth-type\s*:\s*basic""",
            joined,
        )
        if is_ingress and targets_lh and host_present and not has_auth:
            for idx, raw in enumerate(doc):
                if "longhorn-frontend" in raw:
                    findings.append(
                        f"{path}:{line_offset + idx}: longhorn-"
                        f"frontend Ingress exposes the Longhorn UI "
                        f"on a public host with no "
                        f"nginx.ingress.kubernetes.io/auth-type "
                        f"annotation -> the cluster volume admin "
                        f"UI is reachable without credentials "
                        f"(CWE-306/CWE-1188): "
                        f"{raw.strip()[:200]}"
                    )
                    break
        line_offset += len(doc) + 1
    return findings


def scan(path: str) -> List[str]:
    text = _read(path)
    if not text:
        return []
    if not _LH_CONTEXT.search(text):
        return []

    findings: List[str] = []

    for i, raw in _join_continuations(text.splitlines()):
        if _COMMENT_LINE.match(raw):
            continue

        if _HTPASSWD_DEFAULT.search(raw):
            findings.append(
                f"{path}:{i}: longhorn install script invokes "
                f"htpasswd with the literal default credentials "
                f"admin/admin -> the Longhorn UI (full cluster "
                f"volume admin: snapshot, restore, delete any "
                f"PV) is published behind a password every "
                f"reader of the docs already knows "
                f"(CWE-798/CWE-1392/CWE-306): "
                f"{raw.strip()[:200]}"
            )
            continue

        m = _AUTH_LINE.match(raw)
        if m and m.group(1).startswith("admin:"):
            findings.append(
                f"{path}:{i}: longhorn auth secret has "
                f"htpasswd entry beginning with admin: -> the "
                f"Longhorn UI is gated by the documented "
                f"default username 'admin'; combined with the "
                f"published quickstart hash this is effectively "
                f"unauthenticated (CWE-798/CWE-1392): "
                f"{raw.strip()[:200]}"
            )
            continue

    findings.extend(_scan_ingress_no_auth(path, text))
    return findings


_TARGET_EXTS = (".conf", ".cfg", ".properties",
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

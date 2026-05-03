#!/usr/bin/env python3
"""
llm-output-graylog-root-password-sha2-default-detector

Flags Graylog server configurations / docker-compose / Helm values
that ship the **well-known default** ``root_password_sha2`` (the
SHA-256 of the literal string ``admin``):

    8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918

This value is published verbatim in Graylog's official docs and
docker-compose quickstart, so models tend to copy it straight into
production configs. Anyone who knows the hash (i.e. anyone who can
read public docs) can log in as the local ``admin`` superuser and:

  * read every search result, alert, dashboard, and stream (logs
    almost always contain secrets, JWTs, customer PII),
  * create / modify users and roles (full tenant takeover),
  * create input listeners (log injection / pivot into the host
    network) or content packs (RCE-adjacent on some plugins),
  * hit the Graylog REST API and the underlying Elasticsearch /
    OpenSearch via search query exfiltration.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A07:2021 Identification and Authentication Failures

Why LLMs ship this
------------------
The Graylog README, the official ``docker-compose.yml`` in the
``Graylog2/docs`` repo, and almost every "deploy Graylog in 5
minutes" tutorial uses ``GRAYLOG_ROOT_PASSWORD_SHA2`` set to that
exact hash. Models pattern-match "Graylog config" -> emit the
default hash.

Heuristic
---------
We flag the literal SHA-256 of ``admin`` whenever it appears as the
value of a Graylog root-password field. Concretely:

1. **server.conf / .properties style** (``graylog.conf``)::

     root_password_sha2 = 8c6976e5b54...a918

2. **Env / docker-compose / Dockerfile / .env**::

     GRAYLOG_ROOT_PASSWORD_SHA2=8c6976e5b54...a918
     GRAYLOG_ROOT_PASSWORD_SHA2: "8c6976e5b54...a918"

3. **Helm values / k8s manifest** (``graylog.yaml``)::

     graylog:
       rootPasswordSha2: 8c6976e5b54...a918

We also flag the hash when it appears as a bare value next to any
key whose name contains ``root_password_sha2`` or
``rootpasswordsha2`` (case-insensitive, underscores / dashes
ignored).

We do NOT flag:

  * other (non-default) SHA-256 hashes assigned to the same key,
  * the literal hash inside a comment / docstring,
  * the literal hash in a file that has no Graylog context AND no
    key on the same / previous line (we require either a Graylog
    config token in the file or a matching key on the line).

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# SHA-256("admin") -- the published Graylog default.
DEFAULT_ADMIN_SHA256 = (
    "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"
)

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

# Match a line that assigns the default hash to any key whose
# normalized form (lowercase, no underscores / dashes) contains
# ``rootpasswordsha2``.
_KV_LINE = re.compile(
    r"""^\s*(?:export\s+)?([A-Za-z0-9_.\-]+)\s*[:=]\s*"""
    r"""["']?([0-9a-fA-F]{64})["']?\s*(?:[#;].*)?$""",
)

# Helm-style nested key on its own line (we then look at the next
# non-empty value line for the hash).
_YAML_KEY_LINE = re.compile(
    r"""^\s*([A-Za-z0-9_.\-]+)\s*:\s*["']?([0-9a-fA-F]{64})?["']?"""
    r"""\s*(?:#.*)?$""",
)

_GRAYLOG_TOKENS = re.compile(
    r"""(?im)\b(?:graylog|GRAYLOG_)\b""",
)


def _normalize_key(k: str) -> str:
    return re.sub(r"[_\-.]", "", k).lower()


def _key_is_root_pw(k: str) -> bool:
    n = _normalize_key(k)
    return "rootpasswordsha2" in n


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []

    file_has_graylog = bool(_GRAYLOG_TOKENS.search(text))
    findings: List[str] = []

    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        m = _KV_LINE.match(raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2).lower()
        if value != DEFAULT_ADMIN_SHA256:
            continue
        # Either the key is a Graylog root-password key, OR the
        # file as a whole has graylog context AND the key name
        # smells like a password.
        key_is_pw = _key_is_root_pw(key)
        key_pw_ish = "password" in _normalize_key(key)
        if not key_is_pw and not (file_has_graylog and key_pw_ish):
            continue
        findings.append(
            f"{path}:{i}: graylog {key} = SHA-256(\"admin\") "
            f"(the published default) -> anyone with the public "
            f"docs can log in as local admin (CWE-798/CWE-1392/"
            f"CWE-1188): {raw.strip()[:200]}"
        )
    return findings


_TARGET_EXTS = (".conf", ".cfg", ".properties", ".env",
                ".yaml", ".yml", ".json", ".sh", ".bash",
                ".service", ".dockerfile", ".ini")


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

#!/usr/bin/env python3
"""
llm-output-nacos-default-credentials-detector

Flags Nacos (Alibaba's service discovery + dynamic config server)
configurations that ship the **well-known default** administrator
credentials:

    username: nacos
    password: nacos

Nacos's official quickstart, the bundled ``application.properties``,
the published Docker image (``nacos/nacos-server``), and almost every
"set up Nacos in 5 minutes" tutorial uses ``nacos / nacos`` as the
out-of-the-box console login. Models pattern-match "Nacos config" and
emit those literals straight into production manifests / docker-compose
files / Helm values.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A07:2021 Identification and Authentication Failures

What anyone with default Nacos creds gets
-----------------------------------------
The Nacos console at ``/nacos/`` exposes:

  * every dynamic config (DB connection strings, AK/SK pairs,
    feature flags, third-party API tokens) -- in plaintext,
  * service registry -- attacker can register a malicious instance
    and intercept all RPC traffic for a service name (classic
    service-discovery hijack),
  * permission / namespace management -- create a tenant-level admin
    and persist access,
  * config push -- modify any consumer's runtime behaviour
    (RCE-adjacent on Spring Cloud apps via SpEL injection in
    config values, see CVE-2021-29441 / CVE-2021-29442 family).

Heuristic
---------
We flag any of the following on a non-comment line:

1. ``username: nacos`` AND a paired ``password: nacos`` within a
   small window (the typical YAML / properties pattern).
2. ``NACOS_AUTH_*`` style env vars set to the literal ``nacos``.
3. Spring config style ``spring.cloud.nacos.*.username = nacos``
   plus the matching password line.
4. Bare ``-u nacos:nacos`` in shell / curl / Dockerfile commands.

We require Nacos context in the file (any of: ``nacos``,
``NACOS_``, ``spring.cloud.nacos``, ``nacos-server``,
``com.alibaba.nacos``) to avoid flagging unrelated configs that
happen to use the lowercase string ``nacos`` as a username.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

_NACOS_CONTEXT = re.compile(
    r"""(?im)\b(?:nacos|NACOS_|nacos-server|com\.alibaba\.nacos)\b""",
)

# Generic key/value matcher across YAML, .properties, .env.
# Captures key, value (quoted or bare).
_KV = re.compile(
    r"""^\s*(?:-\s+)?(?:export\s+)?([A-Za-z0-9_.][A-Za-z0-9_.\-]*)\s*[:=]\s*"""
    r"""['"]?([A-Za-z0-9_.\-@/+=]+)['"]?\s*(?:[#;].*)?$""",
)

# curl / docker -u nacos:nacos style.
_DASH_U = re.compile(
    r"""(?:^|\s)-u\s+['"]?nacos:nacos['"]?(?:\s|$)""",
)

# Basic-auth URL form: http://nacos:nacos@host
_URL_AUTH = re.compile(
    r"""://nacos:nacos@""",
)

_USERNAME_KEY_FRAGMENTS = ("username", "user", "login")
_PASSWORD_KEY_FRAGMENTS = ("password", "passwd", "pwd", "secret")


def _normalize_key(k: str) -> str:
    return re.sub(r"[_\-.]", "", k).lower()


def _is_nacos_username_key(k: str) -> bool:
    nk = _normalize_key(k)
    if "nacos" not in nk and not any(
        nk.endswith(s) or nk == s for s in _USERNAME_KEY_FRAGMENTS
    ):
        return False
    return any(s in nk for s in _USERNAME_KEY_FRAGMENTS)


def _is_nacos_password_key(k: str) -> bool:
    nk = _normalize_key(k)
    return any(s in nk for s in _PASSWORD_KEY_FRAGMENTS)


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []

    if not _NACOS_CONTEXT.search(text):
        return []

    findings: List[str] = []
    lines = text.splitlines()
    n = len(lines)

    # Track username "nacos" hits; pair with a password "nacos" within
    # a 6-line window forward or backward.
    user_hits: List[Tuple[int, str, str]] = []
    pw_hits: List[Tuple[int, str, str]] = []

    for i, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue

        # Form 4: -u nacos:nacos  OR  ://nacos:nacos@
        if _DASH_U.search(raw) or _URL_AUTH.search(raw):
            findings.append(
                f"{path}:{i}: nacos default basic-auth literal "
                f"'nacos:nacos' (CWE-798/CWE-1392): "
                f"{raw.strip()[:200]}"
            )
            continue

        m = _KV.match(raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        vl = value.lower()
        if vl != "nacos":
            continue
        if _is_nacos_username_key(key):
            user_hits.append((i, key, raw.strip()))
        if _is_nacos_password_key(key):
            pw_hits.append((i, key, raw.strip()))

    # Pair within 6 lines.
    used_users = set()
    used_pws = set()
    for ui, ukey, uraw in user_hits:
        for pi, pkey, praw in pw_hits:
            if pi in used_pws:
                continue
            if abs(pi - ui) <= 6 and pi != ui:
                findings.append(
                    f"{path}:{ui}: nacos default username 'nacos' "
                    f"({ukey}) paired with default password 'nacos' "
                    f"on line {pi} ({pkey}) -- the published "
                    f"out-of-the-box console creds (CWE-798/"
                    f"CWE-1392/CWE-1188): {uraw[:160]}"
                )
                used_users.add(ui)
                used_pws.add(pi)
                break

    # A bare password=nacos with NACOS_ env-var key counts on its own
    # (env-var pattern often sets only the password).
    for pi, pkey, praw in pw_hits:
        if pi in used_pws:
            continue
        nk = _normalize_key(pkey)
        if "nacos" in nk:
            findings.append(
                f"{path}:{pi}: nacos default password literal 'nacos' "
                f"on Nacos-named key '{pkey}' (CWE-798/CWE-1392): "
                f"{praw[:160]}"
            )

    return findings


_TARGET_EXTS = (".conf", ".cfg", ".properties", ".env",
                ".yaml", ".yml", ".json", ".sh", ".bash",
                ".service", ".dockerfile", ".ini", ".toml",
                ".xml")


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

#!/usr/bin/env python3
"""
llm-output-vouch-proxy-jwt-secret-default-detector

Flags **Vouch Proxy** (SSO reverse-proxy used in front of nginx /
traefik to gate apps behind OAuth/OIDC) deployments where
`vouch.jwt.secret` (env: `VOUCH_JWT_SECRET`) is left at the
upstream example placeholder, an obvious weak literal, or an empty
string.

Why it matters
--------------
Vouch Proxy issues a signed JWT cookie after a successful OAuth
flow. Every downstream nginx/traefik just calls Vouch's `/validate`
endpoint, which trusts whatever HMAC-signed JWT presents itself.

If the attacker knows `jwt.secret`, they can forge a JWT for *any*
email/group, present it as the `VouchCookie`, and Vouch will mint
a clean 200 to the proxy. SSO is bypassed for every application
behind Vouch with a single curl.

The upstream `config/config.yml.example` ships with::

    jwt:
      secret: your_random_string

and the env-var template ships with::

    VOUCH_JWT_SECRET=your_random_string

Both literals appear verbatim in copy-pasted "deploy vouch in 5
minutes" tutorials and LLM completions.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-330: Use of Insufficiently Random Values
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-347: Improper Verification of Cryptographic Signature
    (downstream effect: forged JWT accepted)
  - OWASP A02:2021 Cryptographic Failures
  - OWASP A05:2021 Security Misconfiguration
  - OWASP A07:2021 Identification & Authentication Failures

Heuristic
---------
In `vouch*`-named files, `config.y*ml`, `*.env*`, `*.conf`, `*.sh`,
`Dockerfile*`, `docker-compose.*`, `*.toml`, `*.json`, and any file
whose body mentions vouch-proxy scope hints, we flag:

1. A YAML `jwt:` block with `secret: <weak>` underneath, OR
2. An env-style `VOUCH_JWT_SECRET=<weak>` / `VOUCH_JWT_SECRET: <weak>`,

where `<weak>` is one of:

  * empty
  * `your_random_string` (the upstream example)
  * `change_me`, `changeme`, `change-me`, `changeit`
  * `secret`, `password`, `default`, `test`, `demo`, `example`
  * `vouch`, `vouch-proxy`, `jwt`, `jwtsecret`
  * any value < 32 characters (HMAC-SHA256 needs >= 256 bits of
    entropy; we approximate with length).

We do NOT flag:

  * `${...}` / `{{ ... }}` template references.
  * Long high-entropy values (>= 32 chars).
  * `.md` / `.rst` / `.txt` / `.adoc` prose.

Stdlib-only. Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_VOUCH_SCOPE_HINTS = (
    "vouch-proxy",
    "vouch_proxy",
    "vouch:",
    "vouchproxy",
    "vouch.jwt",
    "vouch_jwt",
    "voucher/vouch-proxy",
    "quay.io/vouch/vouch-proxy",
)

# YAML form: under a `jwt:` mapping we expect a `secret:` key.
# We use a two-line stateful walk for YAML to avoid false positives
# on any unrelated `secret:` key.

_ENV_KEY = re.compile(
    r"""(?P<key>VOUCH_JWT_SECRET)\s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]*))""",
    re.VERBOSE,
)

_YAML_SECRET = re.compile(
    r"""^\s*secret\s*:\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s#\n]*))""",
    re.VERBOSE,
)

_YAML_JWT_BLOCK = re.compile(r"^\s*jwt\s*:\s*$")

_WEAK_LITERALS = {
    "",
    "your_random_string",
    "your-random-string",
    "yourrandomstring",
    "change_me", "changeme", "change-me", "changeit",
    "secret", "password", "passwd", "pass",
    "default", "test", "demo", "example",
    "vouch", "vouch-proxy", "vouch_proxy",
    "jwt", "jwtsecret", "jwt_secret", "jwt-secret",
    "12345", "123456", "1234567", "12345678",
    "qwerty", "letmein", "admin", "root",
}

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")
_PROSE_EXTS = (".md", ".rst", ".txt", ".adoc")


def _is_template_ref(v: str) -> bool:
    return "${" in v or v.startswith("$") or "{{" in v


def _file_in_scope(text: str, path: str) -> bool:
    base = os.path.basename(path).lower()
    if "vouch" in base:
        return True
    low = text.lower()
    return any(h in low for h in _VOUCH_SCOPE_HINTS)


def _classify(val: str) -> str:
    v = val.strip().strip('"').strip("'")
    if _is_template_ref(v):
        return "ok"
    if v.lower() in _WEAK_LITERALS:
        return "weak"
    if len(v) < 32:
        return "short"
    return "ok"


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    base = os.path.basename(path).lower()
    if base.endswith(_PROSE_EXTS):
        return []
    if not _file_in_scope(text, path):
        return []

    findings: List[str] = []
    lines = text.splitlines()

    # Pass 1: YAML jwt: -> secret:
    in_jwt = False
    jwt_indent = -1
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        stripped = raw.lstrip()
        cur_indent = len(raw) - len(stripped)
        if _YAML_JWT_BLOCK.match(raw):
            in_jwt = True
            jwt_indent = cur_indent
            continue
        if in_jwt and stripped and cur_indent <= jwt_indent and not stripped.startswith("-"):
            in_jwt = False
        if in_jwt and cur_indent > jwt_indent:
            m = _YAML_SECRET.match(raw.split("#", 1)[0])
            if m:
                val = m.group("dval") or m.group("sval") or m.group("bval") or ""
                kind = _classify(val)
                if kind == "weak":
                    findings.append(
                        f"{path}:{lineno}: vouch-proxy jwt.secret = "
                        f"placeholder {val!r} -> attacker who knows this "
                        f"can forge a Vouch JWT cookie and bypass SSO "
                        f"for every app behind Vouch (CWE-798/CWE-1392/"
                        f"CWE-347): {raw.strip()[:160]}"
                    )
                elif kind == "short":
                    findings.append(
                        f"{path}:{lineno}: vouch-proxy jwt.secret is "
                        f"{len(val.strip())} chars (< 32) -> insufficient "
                        f"entropy for HMAC-SHA256, JWT cookie can be "
                        f"brute-forced offline (CWE-330/CWE-521): "
                        f"{raw.strip()[:160]}"
                    )

    # Pass 2: env-style VOUCH_JWT_SECRET=...
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = raw.split("#", 1)[0]
        for m in _ENV_KEY.finditer(line):
            val = m.group("dval") or m.group("sval") or m.group("bval") or ""
            kind = _classify(val)
            if kind == "weak":
                findings.append(
                    f"{path}:{lineno}: vouch-proxy VOUCH_JWT_SECRET = "
                    f"placeholder {val!r} -> attacker who knows this "
                    f"can forge a Vouch JWT cookie and bypass SSO for "
                    f"every app behind Vouch (CWE-798/CWE-1392/CWE-347): "
                    f"{raw.strip()[:160]}"
                )
            elif kind == "short":
                findings.append(
                    f"{path}:{lineno}: vouch-proxy VOUCH_JWT_SECRET is "
                    f"{len(val.strip())} chars (< 32) -> insufficient "
                    f"entropy for HMAC-SHA256 (CWE-330/CWE-521): "
                    f"{raw.strip()[:160]}"
                )
    return findings


_TARGET_EXTS = (
    ".conf", ".yaml", ".yml", ".ini", ".env", ".env.example",
    ".sh", ".bash", ".dockerfile", ".toml", ".json",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if (
                        "vouch" in low
                        or low.startswith("dockerfile")
                        or low.startswith("docker-compose")
                        or low.endswith(_TARGET_EXTS)
                    ):
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

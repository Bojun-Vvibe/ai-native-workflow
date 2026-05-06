#!/usr/bin/env python3
"""
llm-output-tyk-gateway-secret-default-detector

Flags **Tyk Gateway** deployments where `secret` (the gateway's
admin / management API token) is left at the well-known sample value
or any other obviously-placeholder value.

Tyk's Gateway has a top-level `"secret"` field in `tyk.conf` (and in
the `TYK_GW_SECRET` env var). That secret authenticates every call
to the **gateway's internal API**, including:

  * `POST /tyk/apis/`           — create / overwrite any API
                                  definition
  * `POST /tyk/keys/`           — mint API keys with arbitrary
                                  policies and quotas
  * `POST /tyk/policies/`       — create / overwrite policies
  * `GET  /tyk/health`          — internal health
  * `POST /tyk/reload/group`    — force-reload all gateways
  * `GET  /tyk/oauth/clients/*` — leak OAuth client secrets

Anyone with the gateway secret effectively owns every API behind the
gateway: they can mint full-privilege keys, change rate limits to 0,
add upstream URLs that point at attacker-controlled backends, and
reload the cluster to apply changes immediately.

The Tyk quickstart `tyk.conf` ships with:

    "secret": "352d20ee67be67f6340b4c0605b044b7"

This value (and a small number of close variants) appears in every
Tyk getting-started repo, every "Tyk in 5 minutes" blog post, and
every docker-compose tutorial. It is one of the most-Googled API
gateway sample values in existence. LLMs reproduce it verbatim.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-306: Missing Authentication for Critical Function
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration
  - OWASP A07:2021 Identification & Authentication Failures
  - OWASP API Security Top 10 — API2:2023 Broken Authentication

Heuristic
---------
We flag two concrete forms in `tyk.conf`-style JSON, YAML, env
files, and shell exports:

1. The literal Tyk quickstart secret:
       352d20ee67be67f6340b4c0605b044b7

2. The `secret` / `TYK_GW_SECRET` / `node_secret` keys set to any
   of the obvious placeholder values: `secret`, `tyk`, `tyk-gw`,
   `changeme`, `admin`, `password`, an empty string, or the literal
   word `default`.

We also flag when Tyk is clearly in scope (file mentions a Tyk
image, `tyk.conf`, `tyk-gateway`, or sets `TYK_GW_*`) and the
secret looks like a short hex placeholder (< 32 chars, hex only)
that matches the quickstart shape but is not a real random value.

We do NOT flag:

  * `node_secret` / `secret` set to a long high-entropy value
    (>= 32 chars, mixed case + digits or non-hex content),
  * docs / README mentions of the quickstart string in prose,
  * non-Tyk JSON/YAML files that happen to have a `secret` key.

Stdlib-only. Walks dirs, scans `*.conf`, `*.json`, `*.yaml`,
`*.yml`, `*.ini`, `*.env.example`, `*.sh`, `*.bash`,
`Dockerfile*`, `docker-compose.*`, and any file whose basename
contains `tyk`.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

QUICKSTART_SECRET = "352d20ee67be67f6340b4c0605b044b7"

_TYK_SCOPE_HINTS = (
    "tyk.conf",
    "tyk-gateway",
    "tykio/tyk",
    "tyk_gw_",
    "tyk-gw",
    "image: tyk",
    "tyk_secret",
    '"secret"',  # combined with other hints below
)

_TYK_BIN = re.compile(r"""(?<![A-Za-z0-9_-])tyk(?:-gateway)?(?:[ \t"']|$)""",
                      re.IGNORECASE)
_TYK_IMAGE = re.compile(
    r"""(?:image\s*[:=]\s*["']?|FROM\s+)
        [A-Za-z0-9./_\-]*tyk(?:io)?[A-Za-z0-9./_\-]*""",
    re.IGNORECASE | re.VERBOSE,
)

_SECRET_KEYS = re.compile(
    r"""(?P<key>"secret"|'secret'|secret|node_secret|"node_secret"|
         TYK_GW_SECRET|TYK_GW_NODE_SECRET|TYK_SECRET)
        \s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]+))
        \s*[,}\n]?""",
    re.IGNORECASE | re.VERBOSE,
)

_WEAK_SECRETS = {
    "",
    "secret", "tyk", "tyk-gw", "tykgw", "tyk_gw", "tyk-gateway",
    "changeme", "change-me", "changeit",
    "admin", "root", "guest", "password", "passwd", "pass",
    "default", "test", "demo",
    "12345", "123456", "1234567", "12345678",
    "qwerty", "letmein",
}

_HEX = re.compile(r"""^[0-9a-fA-F]+$""")

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _file_in_scope(text: str, path: str) -> bool:
    low_path = path.lower()
    base = os.path.basename(low_path)
    if "tyk" in base:
        return True
    low = text.lower()
    score = 0
    for hint in _TYK_SCOPE_HINTS:
        if hint in low:
            score += 1
    if score >= 1 and ("tyk" in low):
        return True
    if _TYK_IMAGE.search(text):
        return True
    return False


def _classify_secret(val: str) -> str:
    v = val.strip()
    # Env-var / templating references — assume the real value is
    # injected from a secret store at runtime.
    if "${" in v or v.startswith("$") or "{{" in v:
        return "ok"
    if v == QUICKSTART_SECRET:
        return "quickstart"
    if v.lower() in _WEAK_SECRETS:
        return "weak"
    if len(v) < 16:
        return "short"
    if _HEX.match(v) and len(v) < 32:
        return "short-hex"
    return "ok"


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    if not _file_in_scope(text, path):
        # Even out of scope, the literal quickstart secret in any
        # config file is worth flagging — it is famous enough that
        # any occurrence is almost certainly a copy-paste mistake.
        # But require the file to be a config / shell, not docs.
        base = os.path.basename(path).lower()
        is_config = (
            base.endswith((".conf", ".json", ".yaml", ".yml", ".ini",
                           ".env.example", ".sh", ".bash"))
            or base.startswith("dockerfile")
            or base.startswith("docker-compose")
        )
        if not is_config or QUICKSTART_SECRET not in text:
            return []

    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        # Strip inline JSON5/JS-style line comments.
        line = raw.split("//", 1)[0]
        for m in _SECRET_KEYS.finditer(line):
            key = m.group("key")
            val = m.group("dval") or m.group("sval") or m.group("bval") or ""
            kind = _classify_secret(val)
            if kind == "ok":
                continue
            if kind == "quickstart":
                findings.append(
                    f"{path}:{lineno}: tyk gateway {key} = literal "
                    f"quickstart secret 352d20ee... -> any caller can "
                    f"mint full-privilege API keys via /tyk/keys/ "
                    f"(CWE-798/CWE-1392): {raw.strip()[:160]}"
                )
            elif kind == "weak":
                findings.append(
                    f"{path}:{lineno}: tyk gateway {key} = placeholder "
                    f"value {val!r} -> internal API auth is effectively "
                    f"off (CWE-1392/CWE-306): {raw.strip()[:160]}"
                )
            elif kind == "short":
                findings.append(
                    f"{path}:{lineno}: tyk gateway {key} value is "
                    f"{len(val)} chars (< 16) -> trivially "
                    f"brute-forced (CWE-521): {raw.strip()[:160]}"
                )
            elif kind == "short-hex":
                findings.append(
                    f"{path}:{lineno}: tyk gateway {key} is short hex "
                    f"({len(val)} chars) -> looks like a quickstart "
                    f"variant, not a real random secret (CWE-1392): "
                    f"{raw.strip()[:160]}"
                )
    return findings


_TARGET_EXTS = (
    ".conf", ".json", ".yaml", ".yml", ".ini",
    ".env.example", ".sh", ".bash", ".dockerfile",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if (
                        "tyk" in low
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

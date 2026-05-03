#!/usr/bin/env python3
"""
llm-output-druid-allowall-authenticator-detector

Flags Apache Druid configurations that leave the
``druid.auth.authenticatorChain`` set to ``["allowAll"]`` (the
out-of-the-box default) or that explicitly opt back in to it.
With the ``allowAll`` authenticator, **every** HTTP request to
the Druid Router / Broker / Coordinator / Overlord is treated as
a fully privileged user. That means anyone who can reach the
process can:

  * issue arbitrary SQL via the Broker,
  * submit ingestion specs (which can shell out via
    ``index_parallel`` w/ extension misuse),
  * read or drop any datasource,
  * change cluster runtime properties.

Vendor docs:

  > "By default, Druid uses the AllowAll Authenticator and the
  >  AllowAll Authorizer, which together provide no security."
  >  -- https://druid.apache.org/docs/latest/operations/security-overview

Maps to:

  - CWE-306: Missing Authentication for Critical Function
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-284: Improper Access Control
  - OWASP A01:2021 / A05:2021

Real-world impact: CVE-2021-26919 (Druid SQL ingestion task RCE)
and CVE-2021-25646 (Druid arbitrary code via JavaScript-enabled
config) both required the attacker to reach the HTTP API -- which
``allowAll`` makes trivial.

Why LLMs ship this
------------------
The Druid quickstart and every blog "spin up Druid in 10 minutes"
omit the auth chain entirely (so the default ``allowAll`` is in
force) or explicitly set it to ``["allowAll"]``. Models replay
that pattern into production ``common.runtime.properties`` /
Helm values / Dockerfiles.

Heuristic
---------
We flag a file (Druid config / Helm values / compose / Dockerfile)
when EITHER:

1. ``druid.auth.authenticatorChain = ["allowAll"]`` (or any
   variant: JSON array, comma-separated, single string
   ``allowAll``, or the same value via ``-D`` / env var
   ``druid_auth_authenticatorChain``), OR

2. The file is clearly a Druid runtime config (contains
   ``druid.service``, ``druid.host``, ``druid.zk.service.host``,
   ``druid.metadata.storage.type``, etc.) and **does not set**
   ``druid.auth.authenticatorChain`` at all -- meaning the
   default ``allowAll`` will be in force.

We do NOT flag:

  * configs that set the chain to a non-allowAll value
    (``["MyBasicAuthenticator"]``, ``["kerberos"]``, etc.),
  * comments / docs that mention the bad pattern,
  * non-Druid YAML / properties files (the file-type sniff
    requires Druid-specific keys before we will fire the
    "missing chain" finding).

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

# Druid keys that mark a file as a Druid runtime config.
_DRUID_KEY_HINTS = (
    "druid.service",
    "druid.host",
    "druid.port",
    "druid.zk.service.host",
    "druid.metadata.storage.type",
    "druid.extensions.loadList",
    "druid.processing.numThreads",
    "druid.broker.cache.useCache",
    "druid.coordinator.startDelay",
    "druid.indexer.runner.javaOpts",
)

# Bad: chain explicitly = ["allowAll"] or "allowAll"
_PROP_AUTH_ALLOWALL = re.compile(
    r"""^\s*druid\.auth\.authenticatorChain\s*=\s*\[?\s*["']?allowAll["']?\s*\]?\s*(?:#.*)?$""",
    re.IGNORECASE,
)
# Bad: chain key present but value is the literal allowAll
_JSON_AUTH_ALLOWALL = re.compile(
    r'"druid\.auth\.authenticatorChain"\s*:\s*(?:"allowAll"|\[\s*"allowAll"\s*\])',
    re.IGNORECASE,
)
# YAML-ish helm form: authenticatorChain: ["allowAll"] or allowAll
_YAML_AUTH_ALLOWALL = re.compile(
    r"""^\s*(?:druid\.auth\.)?authenticatorChain\s*:\s*(?:\[\s*["']?allowAll["']?\s*\]|["']?allowAll["']?)\s*(?:#.*)?$""",
    re.IGNORECASE,
)
# Env / CLI: -Ddruid.auth.authenticatorChain=["allowAll"] or
# druid_auth_authenticatorChain=allowAll
_ENV_AUTH_ALLOWALL = re.compile(
    r"""(?:^|\s)(?:export\s+)?(?:-D)?druid[._]auth[._]authenticatorChain\s*=\s*\[?\s*["']?allowAll["']?\s*\]?(?:\s|$|"|')""",
    re.IGNORECASE,
)

# Any non-empty / non-allowAll authenticatorChain assignment
# (used to detect "the chain IS set to something other than
# allowAll" -- that suppresses the missing-key finding).
_ANY_AUTH_CHAIN = re.compile(
    r"""(?:druid\.auth\.|^|\s)authenticatorChain\s*[:=]""",
    re.IGNORECASE,
)
_JSON_ANY_AUTH_CHAIN = re.compile(
    r'"druid\.auth\.authenticatorChain"\s*:',
    re.IGNORECASE,
)


def _strip_shell_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out)


def _strip_comments(text: str) -> str:
    """Strip line-leading # comments to avoid false positives from
    docs that show the bad pattern in commentary."""
    out_lines = []
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            out_lines.append("")
        else:
            out_lines.append(raw)
    return "\n".join(out_lines)


def _looks_like_druid(path: str, text: str) -> bool:
    base = os.path.basename(path).lower()
    if "druid" in base:
        return True
    return any(h in text for h in _DRUID_KEY_HINTS)


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []

    if not _looks_like_druid(path, text):
        return []

    findings: List[str] = []
    stripped = _strip_comments(text)

    # 1) Explicit allowAll
    saw_explicit_allowall = False
    chain_present = False

    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        if _PROP_AUTH_ALLOWALL.match(line):
            findings.append(
                f"{path}:{i}: druid.auth.authenticatorChain="
                f"[\"allowAll\"] -- every HTTP request is treated "
                f"as fully privileged (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            saw_explicit_allowall = True
        if _YAML_AUTH_ALLOWALL.match(line):
            findings.append(
                f"{path}:{i}: druid authenticatorChain: allowAll "
                f"in YAML/Helm values -- no auth (CWE-306/"
                f"CWE-284): {raw.strip()[:160]}"
            )
            saw_explicit_allowall = True
        if _ENV_AUTH_ALLOWALL.search(line):
            findings.append(
                f"{path}:{i}: druid.auth.authenticatorChain="
                f"allowAll baked into env / CLI flag -- no auth "
                f"(CWE-306): {raw.strip()[:160]}"
            )
            saw_explicit_allowall = True
        if _ANY_AUTH_CHAIN.search(line):
            chain_present = True

    # JSON form (whole-file regex)
    if _JSON_AUTH_ALLOWALL.search(stripped):
        for i, raw in enumerate(text.splitlines(), start=1):
            if _COMMENT_LINE.match(raw):
                continue
            if re.search(
                r'"druid\.auth\.authenticatorChain"\s*:\s*'
                r'(?:"allowAll"|\[\s*"allowAll"\s*\])',
                raw, re.IGNORECASE,
            ):
                findings.append(
                    f"{path}:{i}: druid.auth.authenticatorChain="
                    f"\"allowAll\" in JSON config -- no auth "
                    f"(CWE-306): {raw.strip()[:160]}"
                )
                saw_explicit_allowall = True
                break
    if _JSON_ANY_AUTH_CHAIN.search(stripped):
        chain_present = True

    # 2) Druid-y file with NO chain at all -> default allowAll.
    # Only emit this if we did not already emit an explicit
    # allowAll finding, to avoid double-firing.
    # Require that the file actually carries Druid runtime keys
    # *outside of comments* -- a doc file that only mentions
    # druid.* in comments must not fire.
    has_real_druid_key = any(h in stripped for h in _DRUID_KEY_HINTS)
    if (
        not saw_explicit_allowall
        and not chain_present
        and has_real_druid_key
    ):
        base = os.path.basename(path).lower()
        if (
            base.endswith(".properties")
            or base in ("common.runtime.properties",)
            or "druid" in base and base.endswith((".yaml", ".yml",
                                                  ".properties",
                                                  ".conf"))
        ):
            findings.append(
                f"{path}:1: druid runtime config does not set "
                f"druid.auth.authenticatorChain -- the default is "
                f"[\"allowAll\"], which leaves every HTTP endpoint "
                f"unauthenticated (CWE-306/CWE-1188). Set it "
                f"to a real authenticator (basic, kerberos, "
                f"oidc) before exposing the cluster."
            )

    return findings


_TARGET_EXTS = (".properties", ".json", ".yaml", ".yml",
                ".conf", ".env", ".sh", ".bash", ".dockerfile")
_TARGET_NAMES = ("dockerfile",)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES \
                            or low.startswith("dockerfile") \
                            or low.startswith("docker-compose") \
                            or low.startswith("druid") \
                            or "druid" in low:
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
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

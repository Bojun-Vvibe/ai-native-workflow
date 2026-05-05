#!/usr/bin/env python3
"""
llm-output-chronograf-no-auth-detector

Flags Chronograf (InfluxData's UI for InfluxDB / Kapacitor) launched on
a non-loopback bind address with NO OAuth/OIDC provider configured.

Chronograf has NO authentication out of the box. The only supported
multi-user auth is via an external OAuth provider (GitHub, Google,
Heroku, Auth0, generic OIDC). Without it, anyone who can reach the HTTP
port can:

  * Read every dashboard, source, and alert rule.
  * Add new InfluxDB / Kapacitor sources (pivoting onto upstream DBs).
  * Run arbitrary InfluxQL / Flux queries against connected sources.
  * Edit / delete Kapacitor TICKscripts (RCE on the alerting tier).

Authentication is enabled when EITHER:

  * One of the OAuth env vars is set:
      `TOKEN_SECRET` AND a provider client-id/secret pair, e.g.
      `GH_CLIENT_ID` + `GH_CLIENT_SECRET`,
      `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`,
      `GENERIC_CLIENT_ID` + `GENERIC_CLIENT_SECRET` + `GENERIC_AUTH_URL`,
      `HEROKU_CLIENT_ID` + `HEROKU_SECRET`,
      `AUTH0_CLIENT_ID` + `AUTH0_CLIENT_SECRET` + `AUTH0_DOMAIN`.
  * The equivalent CLI flags are passed:
      `--token-secret`, `--github-client-id`, `--google-client-id`,
      `--generic-client-id`, `--auth0-client-id`, `--heroku-client-id`.

A loopback `--host 127.0.0.1` (or `localhost`, `[::1]`) bind is exempt
since that is a single-operator local-dev pattern.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-284: Improper Access Control.
- CWE-1188: Insecure Default Initialization of Resource.

LLMs ship this misconfig because the Chronograf quickstart is a single
`docker run -p 8888:8888 chronograf` line and the upstream Helm /
compose examples rarely include the OAuth env vars.

Stdlib-only. Reads files passed on argv (recurses into dirs).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We scan for invocations of the `chronograf` binary or the
`quay.io/influxdb/chronograf` / `chronograf` image and look at the
surrounding env / args block. For each invocation we require evidence
of an OAuth provider configured (any one of the provider triplets
above). If none and the bind host is non-loopback (or unset, which
defaults to `0.0.0.0`), we emit a finding.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Match the binary or the docker image. We accept:
#   - bare command `chronograf`
#   - image refs `chronograf:1.10`, `quay.io/influxdb/chronograf:1.10`,
#     `docker.io/library/chronograf`
_BIN_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s/\"'\[=]))"
    r"(?P<bin>chronograf)"
    r"(?=[\s\"'\]:\\]|$)"
)

# Bind host capture. Chronograf accepts `--host 0.0.0.0` and `-h 0.0.0.0`.
# Env var equivalent is `HOST=`.
_HOST_FLAG_RE = re.compile(
    r"(?:--host|(?<![A-Za-z])-h)\s*[=\s]\s*['\"]?(?P<addr>[A-Za-z0-9_.\[\]:]+)"
)
_HOST_ENV_RE = re.compile(r"\bHOST\s*[:=]\s*['\"]?(?P<addr>[A-Za-z0-9_.\[\]:]+)")

# OAuth provider env / flag presence. We require BOTH a TOKEN_SECRET (or
# --token-secret) AND a client-id from any provider.
_TOKEN_SECRET_RE = re.compile(
    r"\b(?:TOKEN_SECRET|--token-secret|JWKS_URL|--jwks-url)\b"
)
_PROVIDER_RE = re.compile(
    r"\b("
    r"GH_CLIENT_ID|--github-client-id|"
    r"GOOGLE_CLIENT_ID|--google-client-id|"
    r"GENERIC_CLIENT_ID|--generic-client-id|"
    r"HEROKU_CLIENT_ID|--heroku-client-id|"
    r"AUTH0_CLIENT_ID|--auth0-client-id"
    r")\b"
)

_LOOPBACK_PREFIXES = (
    "127.",
    "localhost",
    "[::1]",
    "::1",
)


def _strip_hash_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        in_s = False
        in_d = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == "#" and not in_s and not in_d:
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def _is_loopback(addr: str) -> bool:
    a = addr.strip().strip("'\"").lower()
    if not a:
        return False
    for p in _LOOPBACK_PREFIXES:
        if a.startswith(p):
            return True
    return False


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _gather_context(text: str, bin_pos: int) -> str:
    line_start = text.rfind("\n", 0, bin_pos) + 1
    end = line_start
    lines_seen = 0
    n = len(text)
    while end < n and lines_seen < 60:
        nl = text.find("\n", end)
        if nl == -1:
            end = n
            break
        end = nl + 1
        lines_seen += 1
        nxt = text[end:end + 80]
        if nxt.strip() == "" and lines_seen > 1:
            break
    return text[line_start:end]


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    seen = set()

    text_nc = _strip_hash_comments(text)

    # File-global auth evidence: env vars are often hoisted out of the
    # service block (e.g. .env file, separate `environment:` map).
    has_token_global = bool(_TOKEN_SECRET_RE.search(text_nc))
    has_provider_global = bool(_PROVIDER_RE.search(text_nc))
    auth_global = has_token_global and has_provider_global

    for bm in _BIN_RE.finditer(text):
        bin_pos = bm.start()
        ctx = _gather_context(text, bin_pos)
        ctx_nc = _strip_hash_comments(ctx)

        # Local context auth evidence wins over global.
        has_token = bool(_TOKEN_SECRET_RE.search(ctx_nc)) or has_token_global
        has_provider = bool(_PROVIDER_RE.search(ctx_nc)) or has_provider_global
        if has_token and has_provider:
            continue
        # auth_global is the same condition; explicit for clarity.
        if auth_global:
            continue

        # Determine bind host. If a host flag/env is present locally,
        # check it; if not specified, Chronograf defaults to 0.0.0.0.
        host_match = _HOST_FLAG_RE.search(ctx_nc) or _HOST_ENV_RE.search(ctx_nc)
        if host_match and _is_loopback(host_match.group("addr")):
            continue

        ln = _line_of(text, bin_pos)
        key = (path, ln)
        if key in seen:
            continue
        seen.add(key)

        bound = host_match.group("addr") if host_match else "0.0.0.0 (default)"
        findings.append(
            f"{path}:{ln}: chronograf bound to {bound!r} with no OAuth "
            f"provider (TOKEN_SECRET + *_CLIENT_ID) configured "
            f"(CWE-306/CWE-284, full read+write on dashboards, sources, "
            f"and Kapacitor TICKscripts)"
        )

    return findings


_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".env",
    ".tf", ".tpl", ".conf", ".toml",
)
_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
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
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

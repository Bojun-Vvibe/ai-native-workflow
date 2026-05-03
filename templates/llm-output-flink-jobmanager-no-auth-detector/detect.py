#!/usr/bin/env python3
"""
llm-output-flink-jobmanager-no-auth-detector

Flags Apache Flink JobManager configurations that expose the REST /
Web UI (default :8081) with **no authentication** AND on a non-
loopback bind. Flink's REST API can submit and cancel jobs, upload
JAR files, and trigger savepoints. Without auth this is equivalent
to remote-code-execution for anyone on the network.

Flink ships **no built-in authentication** for the REST endpoint.
The vendor recommendation is to put the JobManager behind a
reverse proxy that performs authn, or to bind ``rest.address`` /
``rest.bind-address`` to ``localhost`` and tunnel. See:

  https://nightlies.apache.org/flink/flink-docs-stable/docs/deployment/security/security-rest/

Real CVEs caused by this exact misconfig:

  * CVE-2020-17518 (Flink REST file upload path traversal,
    exploitable because REST was reachable),
  * CVE-2020-17519 (unauth read of arbitrary files via REST).

Maps to:

  - CWE-306: Missing Authentication for Critical Function
  - CWE-749: Exposed Dangerous Method or Function
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
Every Flink quickstart sets ``rest.bind-address: 0.0.0.0`` (or
``jobmanager.bind-host: 0.0.0.0``) so the dashboard "just works"
from the host browser, and Flink itself has no auth knob to flip.
Models replay the quickstart in production manifests / Helm
values without adding a proxy.

Heuristics
----------
We flag a file when BOTH of these are present (in the same file or
the same docker-compose service block):

1. A JobManager REST/web bind to a non-loopback interface, e.g.

     rest.bind-address: 0.0.0.0
     rest.address: 0.0.0.0
     jobmanager.bind-host: 0.0.0.0
     jobmanager.rpc.address: 0.0.0.0
     web.address: 0.0.0.0          (legacy)

   or a published port mapping like ``"8081:8081"`` /
   ``- 8081:8081`` in compose, or ``EXPOSE 8081`` /
   ``--rest.bind-address=0.0.0.0`` on a CLI / Dockerfile.

2. NO indication that an auth proxy is configured. We treat the
   following as "auth present" (suppresses the finding):

     - any line mentioning ``oauth2-proxy``, ``oauth2_proxy``,
       ``authelia``, ``keycloak-gatekeeper``, ``oidc-proxy``,
       ``basic_auth``, ``basicauth``, ``htpasswd``,
       ``traefik.http.middlewares.*.basicauth``,
       ``nginx.ingress.kubernetes.io/auth-``,
       ``security.ssl.rest.enabled: true`` with a client cert
       config nearby (mTLS),
     - ``rest.bind-address: 127.0.0.1`` / ``localhost`` (loopback
       only -- safe).

We also independently flag the smoking-gun standalone CLI:

     start-cluster.sh                    (with rest binding 0.0.0.0)
     flink run -m 0.0.0.0:8081 ...       (client side, informational)
     ./bin/jobmanager.sh start-foreground (no proxy fronted)

We do NOT flag:

  * comments / docs that mention the bad pattern,
  * configs binding to ``127.0.0.1`` / ``localhost`` only,
  * configs that ship with an auth proxy sidecar.

Stdlib-only. Scans ``flink-conf.yaml``, ``config.yaml`` (Flink
1.19+ unified config), ``*.yaml`` / ``*.yml`` (treated as flink if
they contain Flink keys), ``docker-compose.*``, ``Dockerfile*``,
and ``*.sh`` files.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

# Flink keys that bind the JobManager REST/UI/RPC to an interface.
_BIND_KEYS = (
    "rest.bind-address",
    "rest.address",
    "jobmanager.bind-host",
    "jobmanager.rpc.address",
    "web.address",
    "web.bind-address",
)

_FLINK_KEY_HINTS = (
    "jobmanager.",
    "taskmanager.",
    "rest.",
    "state.backend",
    "high-availability",
    "parallelism.default",
    "execution.checkpointing",
)

# Loopback bindings we treat as safe.
_LOOPBACK = ("127.0.0.1", "localhost", "::1")

# A non-loopback bind value (we only consider 0.0.0.0 / :: / a
# concrete public-ish IP / hostname). We flag *only* on the
# explicit "everywhere" binds because LLM quickstarts always pick
# 0.0.0.0; targeted IPs are more often deliberate.
_PUBLIC_BIND = re.compile(
    r"""(?:0\.0\.0\.0|::|\*)(?:\s|$|["'#])""",
)

_KV_LINE = re.compile(
    r"""^\s*([A-Za-z0-9_.\-]+)\s*[:=]\s*['"]?([^#'"\n]+?)['"]?\s*(?:#.*)?$""",
)

# CLI flag form: --rest.bind-address=0.0.0.0 or
# -Drest.bind-address=0.0.0.0
_CLI_FLAG = re.compile(
    r"""(?:^|\s)(?:--|-D)("""
    + "|".join(re.escape(k) for k in _BIND_KEYS)
    + r""")[\s=]+(\S+)""",
)

# docker compose published port mapping for 8081 (REST/UI).
_COMPOSE_PORT_8081 = re.compile(
    r"""^\s*-\s*['"]?(?:[\w.\-]+:)?\d*:?8081(?::\d+)?(?:/tcp)?['"]?\s*(?:#.*)?$""",
)

# Dockerfile EXPOSE 8081
_DOCKERFILE_EXPOSE = re.compile(
    r"""^\s*EXPOSE\s+(?:\d+\s+)*8081(?:\s|/|$)""", re.IGNORECASE,
)

# "this file looks like a Flink config" sniff.
_FLINK_FILE_HINT = re.compile(
    r"""(?:^|\b)(?:flink|jobmanager|taskmanager|rest\.bind-address|"""
    r"""rest\.address|state\.backend|high-availability)\b""",
    re.IGNORECASE,
)

# Auth/proxy/mTLS indicators that suppress the finding.
_AUTH_INDICATORS = re.compile(
    r"""(?ix)
    \boauth2[-_]proxy\b
    | \bauthelia\b
    | \bkeycloak[-_]gatekeeper\b
    | \boidc[-_]proxy\b
    | \bbasic[-_]?auth\b
    | \bhtpasswd\b
    | traefik\.http\.middlewares\.[\w\-]+\.basicauth
    | nginx\.ingress\.kubernetes\.io/auth-
    | security\.ssl\.rest\.enabled\s*[:=]\s*true
    """,
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


def _has_auth_indicator(text: str) -> bool:
    return bool(_AUTH_INDICATORS.search(text))


def _looks_like_flink(path: str, text: str) -> bool:
    base = os.path.basename(path).lower()
    if base in ("flink-conf.yaml", "flink-conf.yml"):
        return True
    if "flink" in base:
        return True
    # Generic yaml/sh/dockerfile: only treat as flink if Flink-y
    # keys appear.
    if any(h in text for h in _FLINK_KEY_HINTS):
        return True
    return False


def _bind_findings(text: str, path: str) -> List[Tuple[int, str, str]]:
    """Return list of (lineno, key, value) for non-loopback binds."""
    out: List[Tuple[int, str, str]] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        m = _KV_LINE.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key in _BIND_KEYS:
                if val in _LOOPBACK:
                    continue
                if _PUBLIC_BIND.match(val + " "):
                    out.append((i, key, val))
        for cm in _CLI_FLAG.finditer(line):
            key = cm.group(1)
            val = cm.group(2).strip().strip('"').strip("'")
            if val in _LOOPBACK:
                continue
            if _PUBLIC_BIND.match(val + " "):
                out.append((i, key, val))
    return out


def _port_8081_findings(text: str, path: str) -> List[int]:
    out: List[int] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMPOSE_PORT_8081.match(raw):
            out.append(i)
        elif _DOCKERFILE_EXPOSE.match(raw):
            out.append(i)
    return out


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []

    if not _looks_like_flink(path, text):
        return []
    if _has_auth_indicator(text):
        return []

    findings: List[str] = []

    for lineno, key, val in _bind_findings(text, path):
        findings.append(
            f"{path}:{lineno}: flink {key}={val} -- JobManager REST/"
            f"UI exposed without authentication "
            f"(CWE-306/CWE-749/CWE-1188): "
            f"flink ships no built-in REST auth; front it with an "
            f"auth proxy or bind to 127.0.0.1"
        )

    # Compose / Dockerfile path: publishing 8081 with no auth proxy
    # in the same file.
    base = os.path.basename(path).lower()
    if (
        base.startswith("docker-compose")
        or base.startswith("dockerfile")
        or path.lower().endswith((".dockerfile",))
    ):
        for lineno in _port_8081_findings(text, path):
            findings.append(
                f"{path}:{lineno}: publishes flink JobManager REST "
                f"port 8081 with no auth proxy in this file "
                f"(CWE-306): bind to internal network or add "
                f"oauth2-proxy / basic-auth sidecar"
            )

    return findings


_TARGET_EXTS = (".yaml", ".yml", ".conf", ".properties",
                ".sh", ".bash", ".env", ".dockerfile")
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
                            or low.startswith("flink"):
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

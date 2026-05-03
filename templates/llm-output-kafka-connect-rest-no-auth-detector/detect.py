#!/usr/bin/env python3
"""
llm-output-kafka-connect-rest-no-auth-detector

Flags Apache Kafka Connect worker configurations that expose the
REST API (default :8083) on a non-loopback interface with **no
authentication**. Kafka Connect's REST API can create, update,
pause, resume, and delete connectors -- including connectors that
read from / write to arbitrary external systems and that load
arbitrary plugin classes from the worker's classpath. Without
auth, anyone who can reach :8083 can pivot the worker into a
remote-code-execution surface (CVE-2023-25194 is a famous example
that pivots through a JNDI-aware connector config).

Kafka Connect ships **no built-in REST authentication**. The
upstream guidance is to set ``listeners`` to a ``https://`` URL
plus ``listeners.https.ssl.client.auth=required`` (mTLS), or to
configure a JAAS ``rest.extension.classes`` with
``BasicAuthSecurityRestExtension`` and a credentials file, or to
front the worker with an auth proxy. See:

  https://kafka.apache.org/documentation/#connect_rest

Maps to:

  - CWE-306: Missing Authentication for Critical Function
  - CWE-749: Exposed Dangerous Method or Function
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
Every Kafka Connect quickstart sets ``rest.host.name=0.0.0.0``
(or just ships ``connect-distributed.properties`` with the default
listener that binds everywhere) so the REST API is reachable from
the host browser. Because Kafka Connect itself has no auth knob to
flip, models replay the quickstart wholesale into production
manifests, helm charts, and compose stacks.

Heuristics
----------
We flag a file when BOTH:

1. A Connect worker REST listener bind to a non-loopback
   interface, e.g.

     rest.host.name=0.0.0.0
     listeners=http://0.0.0.0:8083
     listeners=HTTP://:8083              (empty host == all-ifaces)
     rest.advertised.host.name=0.0.0.0   (informational only,
                                          but a strong signal in
                                          combination with
                                          listeners=http://...)

   or a published port mapping like ``"8083:8083"`` /
   ``- 8083:8083`` in compose, or ``EXPOSE 8083`` /
   ``--override rest.host.name=0.0.0.0`` on a CLI / Dockerfile.

2. NO indication that auth is configured. We treat the
   following as "auth present" (suppresses the finding):

     - any line mentioning ``oauth2-proxy``, ``oauth2_proxy``,
       ``authelia``, ``keycloak-gatekeeper``, ``oidc-proxy``,
       ``basic_auth``, ``BasicAuthSecurityRestExtension``,
       ``rest.extension.classes`` with a non-empty value,
       ``htpasswd``, ``traefik.http.middlewares.*.basicauth``,
       ``nginx.ingress.kubernetes.io/auth-``,
     - ``listeners.https.ssl.client.auth`` set to ``required`` or
       ``requested`` (mTLS),
     - listener URL of ``https://`` AND a non-empty
       ``listeners.https.ssl.keystore.location`` (TLS+ usually
       paired with mTLS or an upstream proxy),
     - bind to ``127.0.0.1`` / ``localhost`` (loopback only --
       safe).

We do NOT flag:

  * comments / docs that mention the bad pattern,
  * configs binding to ``127.0.0.1`` / ``localhost`` only,
  * configs that ship with a configured rest extension or
    fronting auth proxy.

Stdlib-only. Scans ``connect-*.properties``, ``worker.properties``,
``*.properties``, ``*.yaml`` / ``*.yml`` (treated as Connect if
they contain Connect keys), ``docker-compose.*``, ``Dockerfile*``,
``*.sh``.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

# Kafka Connect property keys that bind / advertise the REST API.
_BIND_KEYS = (
    "rest.host.name",
    "rest.advertised.host.name",
    "listeners",
)

_CONNECT_KEY_HINTS = (
    "bootstrap.servers",
    "group.id",
    "key.converter",
    "value.converter",
    "config.storage.topic",
    "offset.storage.topic",
    "status.storage.topic",
    "plugin.path",
    "rest.host.name",
    "rest.port",
    "rest.advertised",
)

_LOOPBACK = ("127.0.0.1", "localhost", "::1", "[::1]")

_PUBLIC_BIND_TOKEN = re.compile(
    r"""(?:0\.0\.0\.0|::|\*|\[::\])""",
)

# key=value or key: value (we accept both for portability).
_KV_LINE = re.compile(
    r"""^\s*([A-Za-z0-9_.\-]+)\s*[:=]\s*['"]?([^#'"\n]+?)['"]?\s*(?:#.*)?$""",
)

# Listener URL form: scheme://host:port,scheme://host:port
_LISTENER_URL = re.compile(
    r"""(?ix)\b(https?)://([A-Za-z0-9_.\-\[\]:*]*)?:(\d+)\b""",
)

# CLI override form: --override rest.host.name=0.0.0.0
_CLI_OVERRIDE = re.compile(
    r"""(?:^|\s)--override\s+("""
    + "|".join(re.escape(k) for k in _BIND_KEYS)
    + r""")\s*=\s*(\S+)""",
)

# docker compose published port mapping for 8083 (Connect REST).
_COMPOSE_PORT_8083 = re.compile(
    r"""^\s*-\s*['"]?(?:[\w.\-]+:)?\d*:?8083(?::\d+)?(?:/tcp)?['"]?\s*(?:#.*)?$""",
)

# Dockerfile EXPOSE 8083
_DOCKERFILE_EXPOSE = re.compile(
    r"""^\s*EXPOSE\s+(?:\d+\s+)*8083(?:\s|/|$)""", re.IGNORECASE,
)

# Auth/proxy/mTLS indicators that suppress the finding.
_AUTH_INDICATORS = re.compile(
    r"""(?ix)
    \boauth2[-_]proxy\b
    | \bauthelia\b
    | \bkeycloak[-_]gatekeeper\b
    | \boidc[-_]proxy\b
    | \bBasicAuthSecurityRestExtension\b
    | \bhtpasswd\b
    | traefik\.http\.middlewares\.[\w\-]+\.basicauth
    | nginx\.ingress\.kubernetes\.io/auth-
    | listeners\.https\.ssl\.client\.auth\s*[:=]\s*(required|requested)
    """,
)

# rest.extension.classes=<non-empty> (covers BasicAuth or custom).
_REST_EXTENSION_NONEMPTY = re.compile(
    r"""(?im)^\s*rest\.extension\.classes\s*[:=]\s*\S+""",
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
    if _AUTH_INDICATORS.search(text):
        return True
    if _REST_EXTENSION_NONEMPTY.search(text):
        return True
    return False


def _looks_like_connect(path: str, text: str) -> bool:
    base = os.path.basename(path).lower()
    if base.startswith("connect-") and base.endswith(
        (".properties", ".yaml", ".yml")
    ):
        return True
    if base in ("worker.properties",):
        return True
    if "connect" in base and base.endswith(
        (".properties", ".yaml", ".yml")
    ):
        return True
    if any(h in text for h in _CONNECT_KEY_HINTS):
        return True
    return False


def _is_public_host_token(host: str) -> bool:
    h = host.strip()
    if h == "":
        # listeners=http://:8083 -> empty host means all interfaces.
        return True
    if h in _LOOPBACK:
        return False
    if _PUBLIC_BIND_TOKEN.match(h):
        return True
    return False


def _bind_findings(text: str) -> List[Tuple[int, str, str]]:
    """Return list of (lineno, key, value) for non-loopback binds."""
    out: List[Tuple[int, str, str]] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        m = _KV_LINE.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key in ("rest.host.name", "rest.advertised.host.name"):
                if val in _LOOPBACK:
                    continue
                if _PUBLIC_BIND_TOKEN.match(val):
                    out.append((i, key, val))
            elif key == "listeners":
                # listeners=http://0.0.0.0:8083,https://0.0.0.0:8443
                for um in _LISTENER_URL.finditer(val):
                    scheme, host, port = um.group(1), um.group(2) or "", um.group(3)
                    if port != "8083":
                        # Only flag the Connect REST port. (TLS port
                        # is opt-in and usually paired w/ mTLS we
                        # already detect.)
                        continue
                    if scheme.lower() != "http":
                        # https listeners aren't auto-flagged here;
                        # we leave that to mTLS / proxy heuristics.
                        continue
                    if _is_public_host_token(host):
                        out.append((i, "listeners", f"{scheme}://{host}:{port}"))
        for cm in _CLI_OVERRIDE.finditer(line):
            key = cm.group(1)
            val = cm.group(2).strip().strip('"').strip("'")
            if key in ("rest.host.name", "rest.advertised.host.name"):
                if val in _LOOPBACK:
                    continue
                if _PUBLIC_BIND_TOKEN.match(val):
                    out.append((i, key, val))
    return out


def _port_8083_findings(text: str) -> List[int]:
    out: List[int] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMPOSE_PORT_8083.match(raw):
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

    base = os.path.basename(path).lower()
    is_compose_or_docker = (
        base.startswith("docker-compose")
        or "docker-compose" in base
        or base.startswith("dockerfile")
        or path.lower().endswith(".dockerfile")
        or (base.endswith((".yml", ".yaml"))
            and re.search(r"(?i)cp-kafka-connect|debezium/connect|kafka-connect", text) is not None)
    )

    if not is_compose_or_docker and not _looks_like_connect(path, text):
        return []
    if _has_auth_indicator(text):
        return []

    findings: List[str] = []

    if _looks_like_connect(path, text):
        for lineno, key, val in _bind_findings(text):
            findings.append(
                f"{path}:{lineno}: kafka-connect {key}={val} -- "
                f"REST API exposed without authentication "
                f"(CWE-306/CWE-749/CWE-1188): "
                f"connect ships no built-in REST auth; configure "
                f"rest.extension.classes=BasicAuthSecurityRestExtension "
                f"or front with an auth proxy / mTLS"
            )

    if is_compose_or_docker:
        # Only emit the port finding if the file also looks like it
        # is talking about Kafka Connect (image, env keys).
        looks_connect_image = bool(re.search(
            r"(?i)\b(?:cp-kafka-connect|kafka-connect|debezium/connect|strimzi/kafka:.*-connect)\b",
            text,
        )) or any(h in text for h in _CONNECT_KEY_HINTS) or "CONNECT_" in text
        if looks_connect_image:
            for lineno in _port_8083_findings(text):
                findings.append(
                    f"{path}:{lineno}: publishes kafka-connect REST "
                    f"port 8083 with no auth proxy in this file "
                    f"(CWE-306): bind to internal network or add "
                    f"oauth2-proxy / BasicAuthSecurityRestExtension"
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
                            or low.startswith("connect-") \
                            or low.startswith("worker"):
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

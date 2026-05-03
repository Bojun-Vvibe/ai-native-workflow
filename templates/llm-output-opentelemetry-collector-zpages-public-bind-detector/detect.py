#!/usr/bin/env python3
"""
llm-output-opentelemetry-collector-zpages-public-bind-detector

Flags OpenTelemetry Collector configurations whose ``zpages``
extension binds its HTTP debug endpoint (default :55679) to a
non-loopback interface. zpages is an in-process diagnostics UI
that exposes:

  /debug/tracez      -- recent / sampled spans, including
                        attribute values (frequently contains
                        request URLs, user IDs, internal
                        hostnames, error messages with stack
                        traces / SQL fragments / payload data)
  /debug/pipelinez   -- the configured receiver / processor /
                        exporter pipeline topology
  /debug/extensionz  -- enabled extensions and their config

There is **no authentication** on the zpages endpoint. The
upstream contrib doc explicitly warns:

  "Note: zpages should not be exposed to the public internet
   as it can leak sensitive trace data."

  https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/zpagesextension

The shipped example sets ``endpoint: localhost:55679``; LLM
quickstarts almost always rewrite that to ``0.0.0.0:55679`` so
the page is reachable from the host browser.

Maps to:

  - CWE-200: Exposure of Sensitive Information to an
    Unauthorized Actor
  - CWE-306: Missing Authentication for Critical Function
  - CWE-668: Exposure of Resource to Wrong Sphere
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration

Heuristics
----------
We flag a YAML file when:

1. The collector config defines a ``zpages:`` extension block
   under ``extensions:``, AND
2. the extension's ``endpoint`` (or its nested
   ``http: endpoint:``) is bound to a non-loopback interface
   (``0.0.0.0``, ``::``, ``*``, or an empty host like
   ``:55679``), AND
3. the extension is actually enabled in the
   ``service.extensions:`` list (or there's no ``service:``
   block, in which case we still flag because the extension
   would be enabled by default if mentioned in the example).

We also independently flag a ``docker-compose.*`` /
``Dockerfile*`` that publishes / EXPOSEs port ``55679`` from a
file that otherwise looks like an OpenTelemetry Collector
deployment (image name contains ``otel/opentelemetry-collector``
or env vars / args reference the collector).

Suppressed when the same file mentions a fronting auth proxy
(``oauth2-proxy``, ``authelia``, etc.) or when the endpoint is
loopback only (``127.0.0.1`` / ``localhost`` / ``::1``).

Stdlib-only. Scans ``*.yaml`` / ``*.yml`` / ``*.conf``,
``otel-collector*.yaml``, ``docker-compose.*``, ``Dockerfile*``,
``*.sh``.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_LOOPBACK = ("127.0.0.1", "localhost", "::1", "[::1]")

# A "host" token we consider public.
_PUBLIC_HOST = re.compile(
    r"""^(?:0\.0\.0\.0|::|\[::\]|\*)$""",
)

# Endpoint value: host:port. Empty host (":55679") == all-ifaces.
_ENDPOINT_VAL = re.compile(
    r"""^['"]?([A-Za-z0-9_.\-\[\]:*]*?):(\d+)['"]?\s*(?:#.*)?$""",
)

# Auth/proxy indicators that suppress the finding.
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
    """,
)

# Hints that this YAML is an OpenTelemetry Collector config.
_OTEL_HINTS = (
    "receivers:",
    "exporters:",
    "processors:",
    "extensions:",
    "service:",
    "pipelines:",
    "otlp:",
    "otlphttp:",
)

_OTEL_IMAGE = re.compile(
    r"""(?i)otel/opentelemetry-collector(?:[-_]contrib)?(?::[\w.\-]+)?""",
)

_COMPOSE_PORT_55679 = re.compile(
    r"""^\s*-\s*['"]?(?:[\w.\-]+:)?\d*:?55679(?::\d+)?(?:/tcp)?['"]?\s*(?:#.*)?$""",
)

_DOCKERFILE_EXPOSE = re.compile(
    r"""^\s*EXPOSE\s+(?:\d+\s+)*55679(?:\s|/|$)""", re.IGNORECASE,
)


def _strip_yaml_comment(line: str) -> str:
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
    return "".join(out).rstrip()


def _looks_like_otel_collector(text: str) -> bool:
    return sum(1 for h in _OTEL_HINTS if h in text) >= 2


def _indent(line: str) -> int:
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 8
        else:
            break
    return n


def _find_zpages_blocks(lines: List[str]) -> List[Tuple[int, int, int]]:
    """
    Locate ``zpages:`` keys nested directly under an
    ``extensions:`` mapping. Return list of
    (header_lineno, header_indent, block_end_lineno_exclusive).

    We accept variants:
      zpages:
      zpages/foo:        (component instances)
    """
    out: List[Tuple[int, int, int]] = []
    in_extensions = False
    extensions_indent = -1
    for i, raw in enumerate(lines):
        stripped = _strip_yaml_comment(raw)
        if not stripped.strip():
            continue
        ind = _indent(stripped)
        s = stripped.strip()

        if not in_extensions:
            if re.match(r"^extensions\s*:\s*$", s):
                in_extensions = True
                extensions_indent = ind
            continue

        # We're inside extensions:. Detect zpages component header
        # at indent > extensions_indent, immediately under it.
        if ind <= extensions_indent and s and not s.startswith("#"):
            # Left the extensions: mapping (next top-level key).
            in_extensions = False
            extensions_indent = -1
            # Re-evaluate this line.
            if re.match(r"^extensions\s*:\s*$", s):
                in_extensions = True
                extensions_indent = ind
            continue

        m = re.match(r"^(zpages(?:/[\w\-]+)?)\s*:\s*(.*)$", s)
        if m:
            header_indent = ind
            # Find the end of this component block (next sibling at
            # same or shallower indent, but still inside extensions).
            end = len(lines)
            for j in range(i + 1, len(lines)):
                rj = _strip_yaml_comment(lines[j])
                if not rj.strip():
                    continue
                indj = _indent(rj)
                if indj <= header_indent:
                    end = j
                    break
            out.append((i, header_indent, end))
    return out


def _block_endpoint_findings(
    lines: List[str], start: int, end: int, header_indent: int
) -> List[Tuple[int, str]]:
    """
    Inside lines[start:end] (where start is the zpages: header),
    find an `endpoint:` value. Accept either:

      zpages:
        endpoint: 0.0.0.0:55679

    or the (less common but supported) nested form:

      zpages:
        http:
          endpoint: 0.0.0.0:55679
    """
    out: List[Tuple[int, str]] = []
    for i in range(start + 1, end):
        raw = _strip_yaml_comment(lines[i])
        s = raw.strip()
        m = re.match(r"^endpoint\s*:\s*(.+?)\s*$", s)
        if not m:
            continue
        val = m.group(1).strip()
        em = _ENDPOINT_VAL.match(val)
        if not em:
            continue
        host = em.group(1)
        if host == "" or _PUBLIC_HOST.match(host):
            out.append((i + 1, val))
        elif host in _LOOPBACK:
            continue
    return out


def _zpages_enabled_in_service(text: str, lines: List[str]) -> bool:
    """
    Return True if the service.extensions: list contains an entry
    starting with 'zpages', OR there's no service: block at all
    (treat as 'would be enabled by default in this snippet').
    """
    if "service:" not in text:
        return True
    in_service = False
    in_ext_list = False
    service_indent = -1
    ext_indent = -1
    for raw in lines:
        s = _strip_yaml_comment(raw)
        if not s.strip():
            continue
        ind = _indent(s)
        body = s.strip()
        if not in_service:
            if re.match(r"^service\s*:\s*$", body):
                in_service = True
                service_indent = ind
            continue
        if ind <= service_indent and not in_ext_list:
            # left service:
            return False
        if not in_ext_list:
            if re.match(r"^extensions\s*:\s*(\[.*\])?\s*$", body):
                # inline list?
                inline = re.match(
                    r"^extensions\s*:\s*\[(.*)\]\s*$", body
                )
                if inline:
                    items = [
                        x.strip().strip("'\"")
                        for x in inline.group(1).split(",")
                    ]
                    return any(it.startswith("zpages") for it in items)
                in_ext_list = True
                ext_indent = ind
            continue
        # Inside extensions: list.
        if ind <= ext_indent:
            return False
        m = re.match(r"^-\s*(\S+)", body)
        if m:
            name = m.group(1).strip().strip("'\"")
            if name.startswith("zpages"):
                return True
    return False


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []

    base = os.path.basename(path).lower()
    lines = text.splitlines()
    findings: List[str] = []

    if _AUTH_INDICATORS.search(text):
        return []

    is_compose_or_docker = (
        base.startswith("docker-compose")
        or "docker-compose" in base
        or base.startswith("dockerfile")
        or path.lower().endswith(".dockerfile")
    )

    if _looks_like_otel_collector(text):
        blocks = _find_zpages_blocks(lines)
        if blocks and _zpages_enabled_in_service(text, lines):
            for hi, hind, end in blocks:
                eps = _block_endpoint_findings(lines, hi, end, hind)
                for lineno, val in eps:
                    findings.append(
                        f"{path}:{lineno}: opentelemetry-collector "
                        f"zpages extension endpoint={val} -- "
                        f"unauth debug UI exposing trace data "
                        f"and pipeline topology "
                        f"(CWE-200/CWE-306/CWE-668/CWE-1188): "
                        f"bind to 127.0.0.1 or remove from "
                        f"service.extensions"
                    )

    if is_compose_or_docker and _OTEL_IMAGE.search(text):
        for i, raw in enumerate(lines, start=1):
            if _COMPOSE_PORT_55679.match(raw) \
                    or _DOCKERFILE_EXPOSE.match(raw):
                findings.append(
                    f"{path}:{i}: publishes opentelemetry-collector "
                    f"zpages port 55679 (CWE-200/CWE-306): zpages "
                    f"has no auth and leaks span data; do not "
                    f"publish externally"
                )

    return findings


_TARGET_EXTS = (".yaml", ".yml", ".conf",
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
                            or low.startswith("otel"):
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

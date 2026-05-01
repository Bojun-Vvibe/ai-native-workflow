#!/usr/bin/env python3
"""Detect Spring Boot Actuator configurations that expose sensitive
management endpoints to the network without authentication-aware narrowing.

Spring Boot ships a powerful "Actuator" surface (``/actuator/env``,
``/heapdump``, ``/threaddump``, ``/loggers``, ``/mappings``,
``/configprops``, ``/beans``, ``/jolokia``, ``/shutdown``, ``/refresh``,
``/restart``, ``/pause``, ``/resume``). When ``management.endpoints.web``
is configured to expose ``*`` (or every dangerous endpoint by name) and
binds to all interfaces, an unauthenticated attacker can read environment
variables (DB passwords, cloud keys), trigger heap dumps containing
secrets, change log levels, or in some configurations execute code via
``/jolokia``/``/env`` POST.

LLM-generated Spring Boot ``application.properties`` /
``application.yml`` / ``bootstrap.yml`` files routinely set::

    management.endpoints.web.exposure.include=*
    management.endpoint.shutdown.enabled=true
    management.endpoint.env.post.enabled=true
    management.security.enabled=false           # Spring Boot 1.x
    management.endpoints.web.cors.allowed-origins=*

This detector flags those wildcard / dangerous-endpoint exposures in
``.properties``, ``.yml``, and ``.yaml`` config files.

CWE refs:
  - CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-306: Missing Authentication for Critical Function

False-positive surface:
  - Local-dev profiles intentionally exposing actuator behind localhost.
    Suppress per line with a trailing ``# actuator-exposure-allowed``
    comment (works in both .properties and .yml).
  - ``management.endpoints.web.exposure.exclude=*`` (the *exclude* form)
    is safe — only ``include`` is checked.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*actuator-exposure-allowed")

# Endpoints considered dangerous to expose unauthenticated.
DANGEROUS = {
    "env", "heapdump", "threaddump", "loggers", "configprops", "beans",
    "mappings", "shutdown", "jolokia", "refresh", "restart", "pause",
    "resume", "trace", "httptrace", "auditevents", "scheduledtasks",
    "sessions", "liquibase", "flyway", "logfile",
}

# .properties patterns
PROP_INCLUDE_STAR = re.compile(
    r"^\s*management\.endpoints\.web\.exposure\.include\s*[:=]\s*[\"']?\s*\*"
)
PROP_INCLUDE_LIST = re.compile(
    r"^\s*management\.endpoints\.web\.exposure\.include\s*[:=]\s*[\"']?([^\"'#]+)"
)
PROP_SECURITY_OFF = re.compile(
    r"^\s*management\.security\.enabled\s*[:=]\s*[\"']?\s*false\b",
    re.IGNORECASE,
)
PROP_SHUTDOWN_ON = re.compile(
    r"^\s*management\.endpoint\.shutdown\.enabled\s*[:=]\s*[\"']?\s*true\b",
    re.IGNORECASE,
)
PROP_ENV_POST = re.compile(
    r"^\s*management\.endpoint\.env\.post\.enabled\s*[:=]\s*[\"']?\s*true\b",
    re.IGNORECASE,
)
PROP_CORS_STAR = re.compile(
    r"^\s*management\.endpoints\.web\.cors\.allowed-origins\s*[:=]\s*[\"']?\s*\*"
)

# YAML patterns: track context by indent of `management:` / `exposure:`
YAML_INCLUDE_INLINE_STAR = re.compile(
    r"^\s*include\s*:\s*[\"']?\s*\*"
)
YAML_INCLUDE_INLINE_LIST = re.compile(
    r"^\s*include\s*:\s*\[?([^\]\n#]+)"
)
YAML_KEY_VALUE = re.compile(r"^\s*([\w\-]+)\s*:\s*(.*)$")


def _list_has_dangerous(value: str) -> List[str]:
    items = re.split(r"[,\s\[\]]+", value.strip())
    hits = [it for it in items if it and it.lower() in DANGEROUS]
    return hits


def scan_properties(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), start=1):
        if SUPPRESS.search(line):
            continue
        stripped = line.split("#", 1)[0]
        if PROP_INCLUDE_STAR.search(stripped):
            findings.append((i, "actuator exposure.include=* exposes every endpoint"))
            continue
        m = PROP_INCLUDE_LIST.match(stripped)
        if m:
            hits = _list_has_dangerous(m.group(1))
            if hits:
                findings.append((i, f"actuator exposure.include lists dangerous endpoints: {','.join(hits)}"))
                continue
        if PROP_SECURITY_OFF.search(stripped):
            findings.append((i, "management.security.enabled=false disables actuator auth"))
            continue
        if PROP_SHUTDOWN_ON.search(stripped):
            findings.append((i, "management.endpoint.shutdown.enabled=true allows remote shutdown"))
            continue
        if PROP_ENV_POST.search(stripped):
            findings.append((i, "management.endpoint.env.post.enabled=true allows remote env mutation"))
            continue
        if PROP_CORS_STAR.search(stripped):
            findings.append((i, "actuator CORS allowed-origins=* exposes endpoints cross-origin"))
            continue
    return findings


def scan_yaml(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    # Track indentation stack of nested keys so we know when we're inside
    # management.endpoints.web.exposure / .cors / .endpoint.<x>.
    # We model the path as list of (indent, key).
    stack: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS.search(raw):
            continue
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        # Pop stack to current indent
        while stack and stack[-1][0] >= indent:
            stack.pop()
        m = YAML_KEY_VALUE.match(line)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2).strip()
        path = ".".join([k for _, k in stack] + [key])
        # Only consider paths under management.*
        if not path.startswith("management"):
            stack.append((indent, key))
            continue

        if not value:
            stack.append((indent, key))
            continue

        # Dotted shorthand inside YAML, e.g. "management.security.enabled: false"
        full = path

        if full.endswith("endpoints.web.exposure.include"):
            if value.lstrip("\"' [").startswith("*"):
                findings.append((i, "actuator exposure.include=* exposes every endpoint"))
            else:
                hits = _list_has_dangerous(value)
                if hits:
                    findings.append((i, f"actuator exposure.include lists dangerous endpoints: {','.join(hits)}"))
        elif full.endswith("security.enabled") and value.lower().strip("\"'") == "false":
            findings.append((i, "management.security.enabled=false disables actuator auth"))
        elif re.search(r"endpoint\.[\w]+\.shutdown\.enabled$|endpoint\.shutdown\.enabled$", full) and value.lower().strip("\"'") == "true":
            findings.append((i, "management.endpoint.shutdown.enabled=true allows remote shutdown"))
        elif full.endswith("endpoint.env.post.enabled") and value.lower().strip("\"'") == "true":
            findings.append((i, "management.endpoint.env.post.enabled=true allows remote env mutation"))
        elif full.endswith("endpoints.web.cors.allowed-origins"):
            if value.lstrip("\"' [").startswith("*"):
                findings.append((i, "actuator CORS allowed-origins=* exposes endpoints cross-origin"))
        # heuristic: a bare `include: '*'` directly under exposure
        elif key == "include" and any(k == "exposure" for _, k in stack):
            if value.lstrip("\"' [").startswith("*"):
                findings.append((i, "actuator exposure.include=* exposes every endpoint"))
            else:
                hits = _list_has_dangerous(value)
                if hits:
                    findings.append((i, f"actuator exposure.include lists dangerous endpoints: {','.join(hits)}"))
        elif key == "allowed-origins" and any(k == "cors" for _, k in stack):
            if value.lstrip("\"' [").startswith("*"):
                findings.append((i, "actuator CORS allowed-origins=* exposes endpoints cross-origin"))
        elif key == "enabled" and value.lower().strip("\"'") == "true" and any(k == "shutdown" for _, k in stack):
            findings.append((i, "management.endpoint.shutdown.enabled=true allows remote shutdown"))

        stack.append((indent, key))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.properties", "*.yml", "*.yaml"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        suffix = f.suffix.lower()
        if suffix == ".properties":
            hits = scan_properties(source)
        else:
            hits = scan_yaml(source)
            # Some YAML files use dotted shorthand keys; also try props parser.
            hits += scan_properties(source)
            # Dedupe
            seen = set()
            uniq = []
            for h in hits:
                if h not in seen:
                    seen.add(h)
                    uniq.append(h)
            hits = uniq
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

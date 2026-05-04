#!/usr/bin/env python3
"""Detect Kibana configurations that wire the service to Elasticsearch
using the built-in superuser account ``elastic``.

In Elasticsearch, ``elastic`` is the bootstrap superuser account
created on first cluster start. It has unrestricted cluster and
index privileges. The official Kibana docs explicitly recommend
creating a dedicated ``kibana_system`` (or older ``kibana``) service
account for the Kibana → Elasticsearch connection, with the minimum
privileges required to run Kibana.

Wiring Kibana to the cluster as ``elastic`` means:

  - Every Kibana saved-object write, every reporting job, every
    Fleet enrolment, every alert action runs with full superuser
    rights on the cluster.
  - A Kibana RCE / SSRF / template-injection bug (there have been
    several across 7.x and 8.x) immediately becomes a full cluster
    takeover, including the ability to read the security index and
    rotate other users' credentials.
  - The bootstrap password is often the one set with
    ``elasticsearch-setup-passwords`` (or auto-generated and pasted
    into config) and is widely shared among operators, making
    rotation painful and frequently skipped.

This is exactly the misconfiguration ``elasticsearch-setup-passwords
auto`` exists to discourage. Despite that, LLM-generated Kibana
configs frequently emit shapes like::

    elasticsearch.username: "elastic"
    elasticsearch.password: "changeme"

or the ``ELASTICSEARCH_USERNAME=elastic`` env-var equivalent in
``docker-compose.yml`` / ``kibana.env``.

What's checked, per file:

  - YAML / properties-style key ``elasticsearch.username`` whose
    value (after stripping quotes) is exactly ``elastic``
    (case-insensitive).
  - Environment-variable assignment ``ELASTICSEARCH_USERNAME=elastic``
    or ``ELASTICSEARCH_USERNAME: elastic`` (compose, env files,
    Kubernetes manifests).
  - The legacy ``xpack.security.authc.providers`` style is not
    flagged (that's about provider order, not the service account).

Accepted (not flagged):

  - ``elasticsearch.username: kibana_system``
  - ``elasticsearch.username: kibana`` (legacy dedicated account
    name, still distinct from the superuser).
  - Any other non-``elastic`` value.
  - Files containing the comment ``# kibana-elastic-superuser-allowed``
    (intentional lab / single-node demo).
  - Lines where ``elastic`` is part of a longer identifier
    (``elasticadmin``, ``elastic-prod``, ``elastic_app``).

Usage::

    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at
255). Stdout: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*kibana-elastic-superuser-allowed", re.IGNORECASE)

# YAML / properties style:  elasticsearch.username: "elastic"
YAML_RE = re.compile(
    r"""^\s*
        elasticsearch\.username
        \s*[:=]\s*
        (?P<q>['"]?)
        (?P<val>[A-Za-z0-9_.\-]+)
        (?P=q)
        \s*(?:\#.*)?$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Env-var style (docker-compose, .env, k8s manifests):
#   ELASTICSEARCH_USERNAME=elastic
#   ELASTICSEARCH_USERNAME: "elastic"
#   - name: ELASTICSEARCH_USERNAME
#     value: elastic
ENV_INLINE_RE = re.compile(
    r"""(?P<lead>^|\s|-\s|"\s*)
        ELASTICSEARCH_USERNAME
        \s*[:=]\s*
        (?P<q>['"]?)
        (?P<val>[A-Za-z0-9_.\-]+)
        (?P=q)
    """,
    re.VERBOSE,
)

# Two-line k8s-style:
#   - name: ELASTICSEARCH_USERNAME
#     value: elastic
ENV_NAME_RE = re.compile(
    r"""^\s*-?\s*name\s*:\s*
        (?P<q>['"]?)ELASTICSEARCH_USERNAME(?P=q)\s*$
    """,
    re.VERBOSE,
)
ENV_VALUE_RE = re.compile(
    r"""^\s*value\s*:\s*
        (?P<q>['"]?)
        (?P<val>[A-Za-z0-9_.\-]+)
        (?P=q)
        \s*$
    """,
    re.VERBOSE,
)


def _is_elastic(value: str) -> bool:
    return value.strip().lower() == "elastic"


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()
    for idx, raw in enumerate(lines, start=1):
        m = YAML_RE.match(raw)
        if m and _is_elastic(m.group("val")):
            findings.append(
                (
                    idx,
                    "Kibana wired to Elasticsearch as superuser "
                    "'elastic' via elasticsearch.username (CWE-250)",
                )
            )
            continue

        m2 = ENV_INLINE_RE.search(raw)
        if m2 and _is_elastic(m2.group("val")):
            # Avoid matching the two-line k8s pattern (handled below).
            findings.append(
                (
                    idx,
                    "Kibana wired to Elasticsearch as superuser "
                    "'elastic' via ELASTICSEARCH_USERNAME (CWE-250)",
                )
            )
            continue

        if ENV_NAME_RE.match(raw):
            # Look ahead a few lines for the matching `value:`.
            for look in range(idx, min(idx + 5, len(lines))):
                nxt = lines[look]
                vm = ENV_VALUE_RE.match(nxt)
                if vm:
                    if _is_elastic(vm.group("val")):
                        findings.append(
                            (
                                look + 1,
                                "Kibana wired to Elasticsearch as "
                                "superuser 'elastic' via "
                                "ELASTICSEARCH_USERNAME env var "
                                "(CWE-250)",
                            )
                        )
                    break
                # Stop early on a clearly-unrelated dedented line.
                if nxt.strip() and not nxt.startswith(" "):
                    break
    return findings


def _is_kibana_config(path: Path) -> bool:
    name = path.name.lower()
    if name in {"kibana.yml", "kibana.yaml"}:
        return True
    if name.endswith((".yml", ".yaml", ".env", ".conf", ".properties")):
        return True
    if name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml"}:
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_kibana_config(f):
                    targets.append(f)
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
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

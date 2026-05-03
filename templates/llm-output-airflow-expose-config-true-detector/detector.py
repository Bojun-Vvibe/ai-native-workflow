#!/usr/bin/env python3
"""Detect Apache Airflow configuration that enables ``expose_config``.

When ``[webserver] expose_config = True`` (or the env-var form
``AIRFLOW__WEBSERVER__EXPOSE_CONFIG=True``) is set, the Airflow
webserver renders the entire ``airflow.cfg`` over the ``/config``
view. That blob includes the Fernet key (which decrypts every
Connection password and secret Variable), the SQL Alchemy
connection string (DB credentials), the broker / result-backend
URLs, and any secrets-backend kwargs.

Anyone who can authenticate to the webserver — and on misconfigured
deployments anyone at all — can lift the entire credential set in
one HTTP GET. The Airflow default is ``False``; LLM-generated
snippets routinely flip it on "for debugging" and never flip it
back.

This detector also flags:

  * ``expose_config = non-sensitive-only`` (softer message — still
    leaks broker URLs, scheduler config, etc.)
  * Helm-style ``exposeConfig: true`` under a ``webserver:`` key in
    YAML values files.

A file containing the comment marker
``airflow-expose-config-allowed`` is treated as suppressed.
"""

from __future__ import annotations

import os
import re
import sys

SUPPRESS_MARK = "airflow-expose-config-allowed"

TRUTHY = {"true", "1", "yes", "on"}

# `expose_config = <value>` in airflow.cfg / .ini / .env style files.
CFG_LINE = re.compile(
    r"""^[ \t]*expose_config[ \t]*=[ \t]*([^\r\n#;]+)""",
    re.IGNORECASE | re.MULTILINE,
)

# `AIRFLOW__WEBSERVER__EXPOSE_CONFIG=...` in shell / Dockerfile / env.
ENV_LINE = re.compile(
    r"""(?:^|[\s'";])AIRFLOW__WEBSERVER__EXPOSE_CONFIG\s*=\s*['"]?([A-Za-z0-9_\-]+)""",
    re.IGNORECASE | re.MULTILINE,
)

# Helm-style YAML: under a `webserver:` map, an `exposeConfig:` key.
# We accept either the nested form or a flat `webserver.exposeConfig:`.
YAML_NESTED = re.compile(
    r"""(?ms)^[ \t]*webserver[ \t]*:\s*\n((?:[ \t]+.*\n)+)""",
)
YAML_FLAT = re.compile(
    r"""^[ \t]*webserver\.exposeConfig[ \t]*:[ \t]*([A-Za-z0-9_\-"']+)""",
    re.MULTILINE,
)
YAML_INNER = re.compile(
    r"""^[ \t]+exposeConfig[ \t]*:[ \t]*([A-Za-z0-9_\-"']+)""",
    re.MULTILINE,
)


def _classify(val: str) -> str | None:
    v = val.strip().strip('"').strip("'").lower()
    if v in TRUTHY:
        return (
            "expose_config is enabled — the /config webserver view will "
            "render the Fernet key, DB URL, broker URL and secrets "
            "backend config to anyone who can reach the UI"
        )
    if v in {"non-sensitive-only", "non_sensitive_only", "nonsensitiveonly"}:
        return (
            "expose_config = non-sensitive-only still leaks broker URLs, "
            "scheduler config and other operationally sensitive values; "
            "prefer `airflow config list` from a shell instead"
        )
    return None


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    findings: list[str] = []
    seen: set[str] = set()

    for m in CFG_LINE.finditer(text):
        reason = _classify(m.group(1))
        if reason:
            key = ("cfg", reason)
            if key not in seen:
                findings.append(f"{path}: [webserver] {reason}")
                seen.add(key)

    for m in ENV_LINE.finditer(text):
        reason = _classify(m.group(1))
        if reason:
            key = ("env", reason)
            if key not in seen:
                findings.append(
                    f"{path}: AIRFLOW__WEBSERVER__EXPOSE_CONFIG: {reason}"
                )
                seen.add(key)

    for m in YAML_FLAT.finditer(text):
        reason = _classify(m.group(1))
        if reason:
            key = ("yaml-flat", reason)
            if key not in seen:
                findings.append(f"{path}: webserver.exposeConfig: {reason}")
                seen.add(key)

    for block in YAML_NESTED.finditer(text):
        body = block.group(1)
        for m in YAML_INNER.finditer(body):
            reason = _classify(m.group(1))
            if reason:
                key = ("yaml-nested", reason)
                if key not in seen:
                    findings.append(
                        f"{path}: webserver.exposeConfig (nested): {reason}"
                    )
                    seen.add(key)

    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [file ...]", file=sys.stderr)
        return 2
    files: list[str] = []
    for arg in argv[1:]:
        if os.path.isdir(arg):
            for root, _, names in os.walk(arg):
                for name in names:
                    files.append(os.path.join(root, name))
        else:
            files.append(arg)

    total = 0
    for f in files:
        for finding in scan_file(f):
            print(finding)
            total += 1
    return total


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

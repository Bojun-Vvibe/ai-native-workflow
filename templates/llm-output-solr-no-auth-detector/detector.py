#!/usr/bin/env python3
"""Detect Apache Solr deployments configured without authentication
on a network-reachable bind address.

Background
==========

Solr ships with no authentication by default. The recommended secure
posture documented upstream is:

  * Enable an authentication plugin via ``security.json`` at the
    ZooKeeper / Solr Home root (``BasicAuthPlugin`` is the common
    bootstrap choice).
  * If you are running an unauthenticated dev instance, bind it to
    loopback only — `SOLR_JETTY_HOST=127.0.0.1` (or `-Dhost=127.0.0.1`
    / `-Djetty.host=127.0.0.1` on the command line).

LLM-generated snippets routinely:

  * delete the `authentication` block from ``security.json`` (or ship
    a `security.json` with `{"authentication":{}}` / `null`),
  * write `SOLR_JETTY_HOST=0.0.0.0` (or omit it, since the default
    bind is `0.0.0.0`),
  * paste `bin/solr start -p 8983` invocations with no `-Dhost` flag
    and no `security.json` alongside,
  * run ``docker run -p 8983:8983 solr`` with no `SOLR_OPTS` and no
    mounted `security.json`.

Any of these makes the Solr Admin UI — which can read, write, and
trigger arbitrary Velocity / config-API operations — reachable
without a password from anyone who can route to port 8983.

A file containing the comment marker ``solr-no-auth-allowed`` is
treated as suppressed.
"""

from __future__ import annotations

import json
import os
import re
import sys

SUPPRESS_MARK = "solr-no-auth-allowed"

# `SOLR_JETTY_HOST=0.0.0.0` in solr.in.sh / Dockerfile / env.
JETTY_HOST_ANY = re.compile(
    r"""(?:^|[\s'";])SOLR_JETTY_HOST[ \t]*=[ \t]*['"]?(0\.0\.0\.0|::|\*)['"]?""",
    re.IGNORECASE | re.MULTILINE,
)

# `-Dhost=0.0.0.0` / `-Djetty.host=0.0.0.0` on the command line.
DASH_D_HOST_ANY = re.compile(
    r"""-D(?:jetty\.)?host\s*=\s*['"]?(0\.0\.0\.0|::|\*)['"]?""",
    re.IGNORECASE,
)

# `bin/solr start` invocations.
SOLR_START_RE = re.compile(
    r"""\bbin/solr\s+start\b[^\n]*""",
    re.IGNORECASE,
)

# `docker run …  solr(:tag)?` invocations.
DOCKER_RUN_SOLR_RE = re.compile(
    r"""\bdocker\s+run\b[^\n]*\bsolr(?::[A-Za-z0-9._-]+)?\b[^\n]*""",
    re.IGNORECASE,
)

# Filenames that are security.json (treated specially).
SECURITY_JSON_NAMES = {"security.json"}


def _looks_like_loopback_bind(line: str) -> bool:
    return bool(re.search(
        r"""-D(?:jetty\.)?host\s*=\s*['"]?(127\.\d+\.\d+\.\d+|::1|localhost)['"]?""",
        line,
        re.IGNORECASE,
    ))


def _scan_security_json(path: str, text: str) -> list[str]:
    findings: list[str] = []
    try:
        doc = json.loads(text)
    except Exception as exc:
        return [f"{path}: security.json is not valid JSON: {exc}"]
    if not isinstance(doc, dict):
        return [f"{path}: security.json top level must be an object"]
    auth = doc.get("authentication")
    if auth is None:
        findings.append(
            f"{path}: security.json has no 'authentication' block — "
            f"Solr accepts unauthenticated requests"
        )
    elif isinstance(auth, dict) and not auth:
        findings.append(
            f"{path}: security.json 'authentication' block is empty — "
            f"Solr accepts unauthenticated requests"
        )
    elif isinstance(auth, dict):
        cls = auth.get("class")
        if not cls:
            findings.append(
                f"{path}: security.json 'authentication' has no 'class' — "
                f"plugin will not load"
            )
    return findings


def scan_file(path: str) -> list[str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    if SUPPRESS_MARK in text:
        return []

    # Join shell line continuations so `docker run … \\\n  -p …` is one line.
    joined = re.sub(r"\\\n", " ", text)

    findings: list[str] = []

    base = os.path.basename(path).lower()
    if base in SECURITY_JSON_NAMES:
        findings.extend(_scan_security_json(path, text))

    for m in JETTY_HOST_ANY.finditer(joined):
        findings.append(
            f"{path}: SOLR_JETTY_HOST={m.group(1)} — Solr Admin UI "
            f"reachable on every interface"
        )

    for m in DASH_D_HOST_ANY.finditer(joined):
        findings.append(
            f"{path}: -Dhost={m.group(1)} — Solr Admin UI reachable on "
            f"every interface"
        )

    # `bin/solr start` with no -Dhost=loopback (default bind is 0.0.0.0).
    for m in SOLR_START_RE.finditer(joined):
        line = m.group(0)
        if not _looks_like_loopback_bind(line):
            findings.append(
                f"{path}: 'bin/solr start' invocation with no "
                f"-Dhost=127.0.0.1 — defaults to 0.0.0.0 bind"
            )

    # `docker run … solr` with no -p 127.0.0.1:8983:8983 mapping AND
    # no mounted security.json.
    for m in DOCKER_RUN_SOLR_RE.finditer(joined):
        line = m.group(0)
        binds_loopback = bool(re.search(
            r"""-p\s+127\.\d+\.\d+\.\d+:""", line, re.IGNORECASE
        ))
        mounts_security = bool(re.search(
            r"""security\.json""", line, re.IGNORECASE
        ))
        if not binds_loopback and not mounts_security:
            findings.append(
                f"{path}: 'docker run … solr' with no loopback port "
                f"binding and no mounted security.json"
            )

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

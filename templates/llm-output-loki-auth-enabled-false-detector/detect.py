#!/usr/bin/env python3
"""
llm-output-loki-auth-enabled-false-detector

Flags Grafana Loki configurations that set ``auth_enabled: false``
(or pass ``-auth.enabled=false`` on the CLI). When auth is disabled,
Loki trusts the value of the ``X-Scope-OrgID`` header from the
caller and applies **no authentication of any kind** -- any client
that can reach the Loki HTTP API (default port 3100) can:

  * push log lines into any tenant (log injection / poisoning of
    SIEM pipelines and dashboards),
  * query (``/loki/api/v1/query``, ``/query_range``) every tenant's
    log stream, including stack traces with secrets, JWTs, request
    bodies, customer PII, and internal hostnames,
  * delete log series via the compactor delete API
    (``/loki/api/v1/delete``) when retention deletes are enabled,
  * enumerate label keys / values to map the internal topology.

The Loki docs are explicit:

> "Disabling authentication is **not recommended** for production
>  setups. With ``auth_enabled: false``, Loki uses a single tenant
>  called ``fake`` and does not perform any authentication."
>  -- https://grafana.com/docs/loki/latest/operations/authentication/

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-862: Missing Authorization
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
Every Loki "getting started" / docker-compose / Helm-quickstart sets
``auth_enabled: false`` because the docs explicitly tell readers to
do so for local single-tenant trials. Models then paste that block
into production configs without re-reading the warning that follows
it.

Heuristic
---------
We flag three concrete forms in files that look like Loki configs:

1. **YAML top-level key** (``loki.yaml``, ``config.yaml``,
   ``values.yaml``)::

     auth_enabled: false

2. **CLI flag** in Dockerfile CMD, docker-compose ``command:``,
   k8s ``args:``, systemd ``ExecStart=``, shell wrapper::

     loki -config.file=/etc/loki/local-config.yaml -auth.enabled=false

3. **Helm values** under a ``loki:`` block::

     loki:
       auth_enabled: false

We do NOT flag:

  * ``auth_enabled: true`` (correct),
  * comments / docs that mention the bad pattern,
  * files that don't look like Loki configs (we require either the
    filename to hint at Loki, OR the file to contain another Loki-
    specific token like ``ingester:``, ``schema_config:``,
    ``ruler:``, ``frontend_worker:``, or ``loki`` on the CLI line).

Stdlib-only. Walks dirs, scans typical config extensions and
Dockerfiles / compose files.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

# YAML: top-level or nested `auth_enabled: false`.
_YAML_AUTH_FALSE = re.compile(
    r"""^(\s*)auth_enabled\s*:\s*["']?false["']?\s*(?:#.*)?$""",
    re.IGNORECASE,
)

# CLI flag: -auth.enabled=false or --auth.enabled=false (with
# optional surrounding quotes).
_CLI_AUTH_FALSE = re.compile(
    r"""(?:^|[\s"'])--?auth\.enabled[ =]["']?false["']?(?=$|[\s"'])""",
    re.IGNORECASE,
)

# Tokens that strongly suggest the file is a Loki config (any of
# these appearing in the file is enough).
_LOKI_TOKENS = re.compile(
    r"""(?m)^\s*(?:ingester|schema_config|ruler|frontend_worker|"""
    r"""compactor|distributor|querier|query_scheduler|"""
    r"""query_range|chunk_store_config|table_manager|"""
    r"""storage_config|memberlist)\s*:""",
)
_LOKI_FILENAME = re.compile(
    r"""(?:^|/)(?:loki|local-config|loki-config|loki[._-]values)"""
    r"""[._-]?[^/]*$""",
    re.IGNORECASE,
)


def _looks_like_loki(path: str, text: str) -> bool:
    base = os.path.basename(path)
    if _LOKI_FILENAME.search(base):
        return True
    if _LOKI_TOKENS.search(text):
        return True
    # Helm values often have a top-level `loki:` key with nested
    # `auth_enabled:` underneath.
    if re.search(r"""^\s*loki\s*:\s*$""", text, re.MULTILINE):
        return True
    # docker-compose / k8s manifests referencing a Loki image, or
    # shell wrappers that exec the loki binary.
    if re.search(
        r"""(?:image:\s*\S*?/?loki[:\s]|/loki\b|\bexec\s+\S*loki\b|"""
        r"""\bloki\s+-config\.file)""",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


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


def scan_yaml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if not _looks_like_loki(path, text):
        return findings
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if _YAML_AUTH_FALSE.match(raw):
            findings.append(
                f"{path}:{i}: loki auth_enabled: false -> any caller "
                f"on the HTTP API can push/query/delete logs in any "
                f"tenant via X-Scope-OrgID (CWE-306/CWE-862/"
                f"CWE-1188): {raw.strip()[:160]}"
            )
    return findings


def scan_cli(text: str, path: str) -> List[str]:
    findings: List[str] = []
    file_is_loki = _looks_like_loki(path, text)
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        # Either the literal token `loki` is on the same line, or
        # the file as a whole looks like a Loki config / launcher.
        if "loki" not in line.lower() and not file_is_loki:
            continue
        if _CLI_AUTH_FALSE.search(line):
            findings.append(
                f"{path}:{i}: loki CLI flag -auth.enabled=false -> "
                f"single-tenant 'fake' mode, no authentication on "
                f"HTTP API (CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
    return findings


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    low = path.lower()
    out: List[str] = []
    if low.endswith((".yaml", ".yml")):
        out.extend(scan_yaml(text, path))
        # YAML compose / k8s manifests may also have CLI args inside
        # `command:` / `args:` lists.
        out.extend(scan_cli(text, path))
    if low.endswith((".sh", ".bash", ".env", ".service",
                     ".dockerfile")):
        out.extend(scan_cli(text, path))
    base = os.path.basename(low)
    if base.startswith("dockerfile") or \
            base.startswith("docker-compose"):
        out.extend(scan_cli(text, path))
    return out


_TARGET_EXTS = (".yaml", ".yml", ".sh", ".bash", ".env", ".service",
                ".dockerfile")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.startswith("dockerfile") or \
                            low.startswith("docker-compose") or \
                            low.endswith(_TARGET_EXTS):
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

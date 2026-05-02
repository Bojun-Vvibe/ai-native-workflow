#!/usr/bin/env python3
"""
llm-output-traefik-api-insecure-true-detector

Flags Traefik (v2/v3) deployments that enable the dashboard / API in
**insecure mode**. The Traefik option `--api.insecure=true` (or the
file-config equivalent `[api] insecure = true` / `api: { insecure:
true }`) instructs Traefik to expose the entire API and dashboard on
the **`traefik` entrypoint**, the **default port `:8080`**, with
**no authentication, no TLS, no middleware** in front of it.

The Traefik docs say it explicitly:

> "WARNING: Enabling the API in production is not recommended,
>  because it will expose all configuration elements, including
>  sensitive data."
>  -- https://doc.traefik.io/traefik/operations/api/

The API exposes:

  * every router and its rule (paths, hosts, headers, regex),
  * every service and its **backend URL** (often internal addresses
    that should never leak),
  * the configured TLS certificates' subject and SANs,
  * dynamic config providers (Docker socket paths, Consul/Etcd
    endpoints), and
  * health, metrics, and entrypoint topology.

In a multi-tenant or internet-exposed environment that is a full
infrastructure map. Pair it with the Docker provider (which is the
default tutorial) and the API also reveals every container label and
every backend service URL Traefik knows about.

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-419: Unprotected Primary Channel
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-200: Exposure of Sensitive Information to Unauthorized Actor
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
Every "Traefik in 5 minutes" blog post turns on `--api.insecure=true`
because it is the only way to see the dashboard without setting up a
router + middleware + basic-auth. The model copies the demo straight
into a "production" docker-compose / k8s manifest.

Heuristic
---------
We look for the option in three concrete forms:

1. **CLI flag** (Dockerfile CMD/ENTRYPOINT, docker-compose
   `command:`, k8s `args:`, systemd `ExecStart=`, shell wrapper):

     `--api.insecure=true`           -- canonical
     `--api.insecure`                -- bare flag (Traefik treats it as true)
     `--api.insecure true`           -- space form

2. **TOML / file provider** (`traefik.toml`, `*.toml`):

     [api]
       insecure = true

3. **YAML file provider** (`traefik.yaml`, `traefik.yml`,
   `dynamic.yaml`, `static.yaml`, helm values):

     api:
       insecure: true

We do NOT flag:

  * `[api] dashboard = true` on its own (dashboard with a router +
    auth middleware is the supported production pattern),
  * `--api=true` (the API itself, when fronted by a proper router,
    is fine),
  * comments / docs that mention the bad option.

Stdlib-only. Walks dirs, scans `*.toml`, `*.yaml`, `*.yml`, `*.env`,
`*.sh`, `*.bash`, `*.service`, `Dockerfile*`, `docker-compose.*`,
and any file whose basename starts with `traefik`.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# CLI flag: --api.insecure[=|space]true, or bare --api.insecure
_CLI_INSECURE = re.compile(
    r"""--api\.insecure(?:\s*=\s*|\s+)?(true|"true"|'true')?(?=[\s"'\],}#]|$)""",
    re.IGNORECASE,
)

# TOML: section [api] then `insecure = true` before next [section].
_TOML_API_HEADER = re.compile(r"""^\s*\[\s*api\s*\]\s*$""", re.IGNORECASE)
_TOML_ANY_HEADER = re.compile(r"""^\s*\[\s*[A-Za-z0-9_.\-]+\s*\]\s*$""")
_TOML_INSECURE_TRUE = re.compile(
    r"""^\s*insecure\s*=\s*true\s*(?:[#].*)?$""", re.IGNORECASE,
)

# YAML: `api:` then nested `insecure: true`.
_YAML_API_KEY = re.compile(r"""^(\s*)api\s*:\s*(?:#.*)?$""")
_YAML_INSECURE = re.compile(
    r"""^(\s*)insecure\s*:\s*["']?(true|yes|on|1)["']?\s*(?:#.*)?$""",
    re.IGNORECASE,
)
_YAML_DEDENT_KEY = re.compile(r"""^(\s*)[A-Za-z0-9_.-]+\s*:""")

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _strip_shell_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out)


def scan_cli(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        m = _CLI_INSECURE.search(line)
        if not m:
            continue
        val = m.group(1)
        # Bare `--api.insecure` with no value -> Traefik treats as true.
        # `--api.insecure=false` would not match because the value
        # group requires `true` (case-insensitive).
        if val is None:
            # Be conservative: only flag the bare flag if the next
            # token is not literally "false".
            after = line[m.end():].lstrip()
            if after.lower().startswith("false"):
                continue
        findings.append(
            f"{path}:{lineno}: traefik --api.insecure exposes API + "
            f"dashboard with no auth/TLS on default :8080 "
            f"(CWE-306/CWE-200): {raw.strip()[:160]}"
        )
    return findings


def scan_toml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_api = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _TOML_API_HEADER.match(raw):
            in_api = True
            continue
        if in_api and _TOML_ANY_HEADER.match(raw):
            in_api = False
            if _TOML_API_HEADER.match(raw):
                in_api = True
            continue
        if not in_api:
            continue
        if _COMMENT_LINE.match(raw):
            continue
        if _TOML_INSECURE_TRUE.match(raw):
            findings.append(
                f"{path}:{lineno}: traefik [api] insecure = true -> "
                f"unauthenticated API+dashboard on :8080 "
                f"(CWE-306/CWE-200): {raw.strip()[:160]}"
            )
    return findings


def scan_yaml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _YAML_API_KEY.match(lines[i])
        if not m:
            i += 1
            continue
        base_indent = len(m.group(1))
        api_line = i + 1
        j = i + 1
        hit = False
        while j < len(lines):
            line = lines[j]
            if line.strip() == "" or _COMMENT_LINE.match(line):
                j += 1
                continue
            md = _YAML_DEDENT_KEY.match(line)
            if md and len(md.group(1)) <= base_indent:
                break
            mi = _YAML_INSECURE.match(line)
            if mi and len(mi.group(1)) > base_indent:
                findings.append(
                    f"{path}:{j+1}: traefik api: insecure: true under "
                    f"api: block (line {api_line}) -> unauthenticated "
                    f"API+dashboard on :8080 (CWE-306/CWE-200)"
                )
                hit = True
            j += 1
        i = j if j > i else i + 1
        if hit:
            continue
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
    if low.endswith(".toml"):
        out.extend(scan_toml(text, path))
    if low.endswith((".yaml", ".yml")):
        out.extend(scan_yaml(text, path))
        out.extend(scan_cli(text, path))  # compose `command:` etc.
    if low.endswith((".env", ".sh", ".bash", ".service")):
        out.extend(scan_cli(text, path))
    base = os.path.basename(low)
    if base.startswith("dockerfile") or base.startswith("docker-compose") \
            or low.endswith(".dockerfile"):
        out.extend(scan_cli(text, path))
    return out


_TARGET_NAMES = ("dockerfile", "docker-compose.yml", "docker-compose.yaml")
_TARGET_EXTS = (".toml", ".yaml", ".yml", ".env",
                ".sh", ".bash", ".service", ".dockerfile")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES \
                            or low.startswith("dockerfile") \
                            or low.startswith("docker-compose") \
                            or low.startswith("traefik"):
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

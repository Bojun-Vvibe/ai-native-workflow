#!/usr/bin/env python3
"""
llm-output-traefik-insecureskipverify-true-detector

Flags Traefik configurations that disable TLS certificate verification
when proxying to upstream/backend HTTPS services, by setting
`insecureSkipVerify: true` (or the CLI/env equivalents).

Traefik exposes this knob in three places, all of which we flag:

  1. Static config (traefik.yml / traefik.toml):
       serversTransport:
         insecureSkipVerify: true

  2. Dynamic config (file provider, k8s CRD, docker labels):
       tls:
         insecureSkipVerify: true
     -- also `serversTransport.<name>.insecureSkipVerify = true` in TOML.

  3. CLI / env:
       --serverstransport.insecureskipverify=true
       --serversTransport.insecureSkipVerify=true
       TRAEFIK_SERVERSTRANSPORT_INSECURESKIPVERIFY=true

When this is set, Traefik will accept ANY upstream certificate,
including self-signed and attacker-issued ones, defeating the entire
point of HTTPS to the backend. This is a classic LLM "fix" for "x509:
certificate signed by unknown authority" — it makes the error go away
by removing the security check.

Maps to:
- CWE-295: Improper Certificate Validation.
- CWE-297: Improper Validation of Certificate with Host Mismatch.
- OWASP A02:2021 Cryptographic Failures.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
*.yml, *.yaml, *.toml, Dockerfile*, docker-compose.*, *.sh, *.bash,
*.env.example, *.service, and Helm template files).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# YAML form: `insecureSkipVerify: true` (any indentation, any case
# variant Traefik accepts: `insecureSkipVerify`, `insecureskipverify`).
_YAML_ISV = re.compile(
    r"""(?im)^\s*insecure[Ss]kip[Vv]erify\s*:\s*(?:true|"true"|'true'|yes|on)\b"""
)

# TOML form: `insecureSkipVerify = true` under `[serversTransport]`
# or `[tls.options.<name>]`. We flag any `insecureSkipVerify = true`
# in a .toml file -- there is no other Traefik-relevant meaning.
_TOML_ISV = re.compile(
    r"""(?im)^\s*insecure[Ss]kip[Vv]erify\s*=\s*true\b"""
)

# CLI / env form (any case, with or without leading dashes, with or
# without a value -- bare `--serverstransport.insecureskipverify`
# defaults to true in Traefik's pflag handling).
_CLI_ISV = re.compile(
    r"""(?i)
    (?:^|[\s"'=])
    -{1,2}serverstransport\.insecureskipverify
    (?:\s*=\s*true|\s+true|\b)
    """,
    re.VERBOSE,
)

_ENV_ISV = re.compile(
    r"""(?i)\bTRAEFIK_SERVERSTRANSPORT_INSECURESKIPVERIFY\s*[=:]\s*(?:true|"true"|'true'|1|yes|on)\b"""
)

# Docker label form Traefik v2/v3 dynamic config:
#   traefik.http.serversTransports.<name>.insecureSkipVerify=true
_LABEL_ISV = re.compile(
    r"""(?i)traefik\.http\.serverstransports?\.[\w-]+\.insecureskipverify\s*[=:]\s*(?:true|"true"|'true'|1|yes|on)\b"""
)

_PATTERNS = [
    ("yaml-insecureSkipVerify-true", _YAML_ISV),
    ("toml-insecureSkipVerify-true", _TOML_ISV),
    ("cli-serverstransport-insecureskipverify", _CLI_ISV),
    ("env-TRAEFIK_SERVERSTRANSPORT_INSECURESKIPVERIFY", _ENV_ISV),
    ("docker-label-insecureSkipVerify-true", _LABEL_ISV),
]

_COMMENT_LEADERS = ("#", "//", ";")

_INTERESTING_SUFFIXES = (
    ".yml", ".yaml", ".toml", ".sh", ".bash", ".service",
    ".env.example", ".tf", ".tfvars",
)
_INTERESTING_NAMES = ("Dockerfile",)


def _looks_interesting(path: str) -> bool:
    base = os.path.basename(path)
    if base.startswith("docker-compose") or base.startswith("traefik"):
        return True
    for n in _INTERESTING_NAMES:
        if base == n or base.startswith(n + "."):
            return True
    for s in _INTERESTING_SUFFIXES:
        if base.endswith(s):
            return True
    # Helm template files
    if base.endswith(".tpl") or base.endswith(".yaml.j2"):
        return True
    return False


def _iter_files(args: Iterable[str]) -> Iterable[str]:
    for a in args:
        if os.path.isdir(a):
            for root, _dirs, files in os.walk(a):
                for f in files:
                    p = os.path.join(root, f)
                    if _looks_interesting(p):
                        yield p
        else:
            yield a


def _strip_comment(line: str) -> str:
    # Strip trailing line comments but keep the code half. Be careful not
    # to strip `#` inside quoted strings.
    in_s: str = ""
    out = []
    i = 0
    while i < len(line):
        c = line[i]
        if in_s:
            out.append(c)
            if c == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if c == in_s:
                in_s = ""
            i += 1
            continue
        if c in ("'", '"'):
            in_s = c
            out.append(c)
            i += 1
            continue
        if c == "#":
            break
        if c == "/" and i + 1 < len(line) and line[i + 1] == "/":
            break
        out.append(c)
        i += 1
    return "".join(out)


def scan_file(path: str) -> List[str]:
    findings: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, 1):
                stripped = raw.lstrip()
                if any(stripped.startswith(c) for c in _COMMENT_LEADERS):
                    continue
                line = _strip_comment(raw)
                for label, pat in _PATTERNS:
                    if pat.search(line):
                        findings.append(
                            f"{path}:{lineno}: {label}: {raw.rstrip()}"
                        )
                        break
    except OSError as e:
        print(f"{path}: read error: {e}", file=sys.stderr)
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detect.py <file-or-dir> [<file-or-dir> ...]",
            file=sys.stderr,
        )
        return 2
    any_hit = False
    for path in _iter_files(argv[1:]):
        for line in scan_file(path):
            print(line)
            any_hit = True
    return 1 if any_hit else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""
llm-output-ollama-host-public-bind-detector

Flags Ollama configurations that bind the model API to a
non-loopback address. Ollama exposes:

  * /api/generate, /api/chat   - run any pulled model
  * /api/pull                  - pull arbitrary models from the
                                 default registry (egress + disk)
  * /api/create, /api/copy,
    /api/delete                - manage local models
  * /api/embeddings            - generate embeddings (CPU/GPU burn)
  * /api/show                  - leak local model inventory

Ollama has **no built-in authentication and no TLS**. The README
explicitly says the API is intended for localhost. The most
copy-pasted homelab snippets are:

    OLLAMA_HOST=0.0.0.0 ollama serve
    OLLAMA_HOST=0.0.0.0:11434 ollama serve

paired with `docker run -e OLLAMA_HOST=0.0.0.0:11434 ...` so the
container's exposed port is reachable from the LAN (or the
internet, when port-forwarded). Once exposed, anyone can:

  * burn the host's GPU / CPU running prompts,
  * pull multi-GB models to fill the disk,
  * exfiltrate any local context the operator has stored,
  * use the host as a free LLM gateway.

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-668: Exposure of Resource to Wrong Sphere
  - CWE-770: Allocation of Resources Without Limits or Throttling
  - OWASP A01:2021 Broken Access Control
  - OWASP A05:2021 Security Misconfiguration

Heuristic
---------
We scan environment-style files, shell scripts, systemd units,
Dockerfiles, and docker-compose files for `OLLAMA_HOST` set to a
non-loopback value. Forms covered:

  env-style:
    OLLAMA_HOST=0.0.0.0
    OLLAMA_HOST=0.0.0.0:11434
    OLLAMA_HOST=:11434              (bare port)
    OLLAMA_HOST=*:11434
    OLLAMA_HOST=192.168.1.10:11434
    OLLAMA_HOST=[::]:11434

  shell:
    export OLLAMA_HOST=0.0.0.0
    OLLAMA_HOST=0.0.0.0:11434 ollama serve

  systemd:
    Environment="OLLAMA_HOST=0.0.0.0"
    Environment=OLLAMA_HOST=0.0.0.0:11434

  Dockerfile:
    ENV OLLAMA_HOST=0.0.0.0:11434
    ENV OLLAMA_HOST 0.0.0.0:11434

  docker-compose:
    environment:
      OLLAMA_HOST: 0.0.0.0:11434
      - OLLAMA_HOST=0.0.0.0:11434

Not flagged:
  * OLLAMA_HOST=127.0.0.1
  * OLLAMA_HOST=127.0.0.1:11434
  * OLLAMA_HOST=localhost:11434
  * OLLAMA_HOST=::1
  * OLLAMA_HOST=[::1]:11434
  * commented-out lines

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_LOOPBACK_HOSTS = {
    "127.0.0.1",
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "::1",
    "[::1]",
}


def _classify_bind(value: str) -> Tuple[bool, str]:
    """Return (is_public, reason). is_public=False means safe."""
    v = value.strip().strip('"').strip("'").strip()
    if not v:
        return (False, "empty")

    # bare port: ":11434"
    if v.startswith(":") and v[1:].isdigit():
        return (True, "bare port (binds all interfaces)")

    # "*:11434" or "*"
    if v == "*" or v.startswith("*:"):
        return (True, "wildcard host *")

    # 0.0.0.0 / 0.0.0.0:port
    if v == "0.0.0.0" or v.startswith("0.0.0.0:"):
        return (True, "0.0.0.0 (all IPv4 interfaces)")

    # [::]:port  / [::]
    if v == "[::]" or v.startswith("[::]:"):
        return (True, "[::] (all IPv6 interfaces)")

    # bare port number
    if v.isdigit():
        return (True, "bare port number (binds all interfaces)")

    # bracketed IPv6 [addr]:port
    if v.startswith("["):
        end = v.find("]")
        if end > 0:
            host = v[1:end].lower()
            if host in _LOOPBACK_HOSTS or host == "::1":
                return (False, "ipv6 loopback")
            if host in ("::", "0:0:0:0:0:0:0:0"):
                return (True, "[::] (all IPv6 interfaces)")
            return (True, f"non-loopback IPv6 host {host}")

    # plain host or host:port
    if ":" in v and not v.count(":") > 1:
        host, _, _port = v.rpartition(":")
        host = host.lower()
        if host in _LOOPBACK_HOSTS:
            return (False, "loopback host")
        if host == "" or host == "*" or host == "0.0.0.0":
            return (True, "wildcard / all-interfaces host")
        return (True, f"non-loopback host {host}")

    # bare host (no port)
    host_only = v.lower()
    if host_only in _LOOPBACK_HOSTS:
        return (False, "loopback host")
    return (True, f"non-loopback host {host_only}")


_COMMENT_LINE = re.compile(r"""^\s*[#;]""")

# OLLAMA_HOST=value  (env, shell export, Dockerfile ENV)
_KV_PAT = re.compile(
    r"""(?:^|[\s;])(?:export\s+|ENV\s+|Environment\s*=\s*"?)?"""
    r"""OLLAMA_HOST\s*[=]\s*"""
    r"""(?P<val>"[^"]*"|'[^']*'|[^\s"';]+)""",
    re.IGNORECASE,
)

# Dockerfile space-form: ENV OLLAMA_HOST 0.0.0.0:11434
_ENV_SPACE_PAT = re.compile(
    r"""^\s*ENV\s+OLLAMA_HOST\s+(?P<val>"[^"]*"|'[^']*'|\S+)""",
    re.IGNORECASE,
)

# YAML mapping form: OLLAMA_HOST: value  (docker-compose env block)
_YAML_PAT = re.compile(
    r"""^\s*-?\s*OLLAMA_HOST\s*:\s*(?P<val>"[^"]*"|'[^']*'|[^\s#].*?)\s*(?:#.*)?$""",
    re.IGNORECASE,
)


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if (v.startswith('"') and v.endswith('"')) or \
            (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]
    return v


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        # Dockerfile ENV K V form
        m = _ENV_SPACE_PAT.match(raw)
        if m:
            val = _strip_quotes(m.group("val"))
            is_public, reason = _classify_bind(val)
            if is_public:
                findings.append(
                    f"{path}:{lineno}: ollama `ENV OLLAMA_HOST "
                    f"{val}` -> {reason}; unauthenticated model "
                    f"API exposed to anyone reachable on port "
                    f"(CWE-306/CWE-770)."
                )
            continue

        # YAML mapping (docker-compose environment: OLLAMA_HOST: ...)
        m = _YAML_PAT.match(raw)
        if m:
            val = _strip_quotes(m.group("val"))
            is_public, reason = _classify_bind(val)
            if is_public:
                findings.append(
                    f"{path}:{lineno}: ollama yaml `OLLAMA_HOST: "
                    f"{val}` -> {reason}; unauthenticated model "
                    f"API exposed (CWE-306)."
                )
            continue

        # General KEY=VALUE form
        for m in _KV_PAT.finditer(raw):
            val = _strip_quotes(m.group("val"))
            is_public, reason = _classify_bind(val)
            if is_public:
                findings.append(
                    f"{path}:{lineno}: ollama `OLLAMA_HOST="
                    f"{val}` -> {reason}; unauthenticated model "
                    f"API; anyone reachable can run inference, "
                    f"pull arbitrary models, list local models "
                    f"(CWE-306/CWE-668/CWE-770)."
                )
    return findings


_TARGET_EXTS = (".sh", ".bash", ".zsh", ".service", ".yaml", ".yml",
                ".envfile", ".environment", ".dockerfile", ".conf")


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    return scan_text(text, path)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.endswith(_TARGET_EXTS) \
                            or low.startswith("dockerfile") \
                            or low.startswith("docker-compose") \
                            or low.startswith("ollama"):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    seen = set()
    for path in iter_paths(argv[1:]):
        for line in scan(path):
            if line in seen:
                continue
            seen.add(line)
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

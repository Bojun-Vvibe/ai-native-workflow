#!/usr/bin/env python3
"""Detect Woodpecker CI server / agent configurations from LLM output
that ship the shared agent RPC secret as empty, missing, or one of a
small set of well-known placeholder values.

Woodpecker (https://woodpecker-ci.org) is a self-hosted, fork of
Drone CI. The server and every agent process authenticate to each
other over gRPC using a single shared secret named
``WOODPECKER_AGENT_SECRET`` (older docs / charts: ``WOODPECKER_SECRET``
or, on the agent side, ``WOODPECKER_SERVER_SECRET``). If that secret
is empty, set to a public-example placeholder, or hard-coded to a
short value, anyone who can reach the server's gRPC port (default
``9000``) can register a rogue agent. Rogue agents receive real
pipeline workloads, which routinely include:

  * deploy keys / cloud credentials injected as pipeline secrets
  * the source tree of every repository the server is wired to
  * the ability to publish artifacts back through the server

This detector flags four orthogonal regressions across the three
config surfaces Woodpecker actually uses:

  1. ``docker-compose.yml`` / ``compose.yaml`` env block:
     ``WOODPECKER_AGENT_SECRET`` set to ``""``, missing while a
     ``woodpecker-agent`` service exists, or set to a value in a
     curated weak-set (``changeme``, ``secret``, ``woodpecker``,
     ``test``, ``admin``, etc., or shorter than 16 chars).
  2. Helm ``values.yaml``: ``agent.secret``, ``server.agent.secret``,
     or ``env.WOODPECKER_AGENT_SECRET`` set to one of the same weak
     values, or to the literal Helm template default
     ``"<changeme>"`` / ``"REPLACE_ME"``.
  3. Shell / systemd ``EnvironmentFile`` / ``.env``:
     ``WOODPECKER_AGENT_SECRET=`` (empty RHS) or
     ``WOODPECKER_AGENT_SECRET=changeme``.
  4. Server-only deployments where ``WOODPECKER_AGENT_SECRET`` is
     absent but ``WOODPECKER_HOST`` (or ``WOODPECKER_GRPC_ADDR``) is
     set to a non-localhost value — the server will still accept
     agent registrations with an empty secret and is reachable from
     the network.

Suppression: a top-of-file comment
``# woodpecker-agent-secret-weak-allowed`` silences all rules for
that file (use only for an isolated lab or an integration-test
fixture).

CWE refs:
  * CWE-321: Use of Hard-coded Cryptographic Key
  * CWE-798: Use of Hard-coded Credentials
  * CWE-1188: Insecure Default Initialization of Resource

Public API:
    scan(text: str) -> list[tuple[int, str]]

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding (capped 255).
    Stdout: ``<file>:<line>:<reason>``.

Stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*woodpecker-agent-secret-weak-allowed", re.IGNORECASE)

WEAK_SECRETS = {
    "",
    "changeme",
    "change-me",
    "<changeme>",
    "<change-me>",
    "replaceme",
    "replace_me",
    "replace-me",
    "<replaceme>",
    "<replace-me>",
    "secret",
    "supersecret",
    "woodpecker",
    "woodpeckersecret",
    "woodpecker-secret",
    "agentsecret",
    "agent-secret",
    "admin",
    "test",
    "testing",
    "demo",
    "example",
    "password",
    "12345",
    "123456",
    "1234567",
    "12345678",
    "todo",
    "<todo>",
    "placeholder",
    "<placeholder>",
}

MIN_LEN = 16
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}

# ---- helpers ---------------------------------------------------------


def _strip_yaml_comment(line: str) -> str:
    out: List[str] = []
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


def _unquote(val: str) -> str:
    v = val.strip()
    if (v.startswith('"') and v.endswith('"')) or (
        v.startswith("'") and v.endswith("'")
    ):
        return v[1:-1]
    return v


def _is_weak(value: str) -> Tuple[bool, str]:
    v = value.strip()
    low = v.lower()
    if low in WEAK_SECRETS:
        return True, f"value {v!r} is a known weak/placeholder secret"
    if len(v) < MIN_LEN:
        return True, f"secret length {len(v)} < minimum {MIN_LEN}"
    return False, ""


def _host_is_remote(value: str) -> bool:
    v = value.strip().strip("'").strip('"')
    if not v:
        return False
    # strip scheme
    v = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", v)
    # split host:port
    host = v.split("/", 1)[0].split(":", 1)[0]
    if not host:
        return False
    return host.lower() not in LOCAL_HOSTS


# ---- env / .env / shell / systemd EnvironmentFile -------------------

ENV_LINE = re.compile(
    r"""(?ix)
    ^\s*
    (?:export\s+)?
    (?P<key>WOODPECKER_[A-Z0-9_]+)
    \s*=\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s#]*)
    \s*(?:\#.*)?$
    """
)


def _scan_envfile(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    secret_seen = False
    host_seen_remote: Optional[Tuple[int, str]] = None
    for i, raw in enumerate(source.splitlines(), start=1):
        m = ENV_LINE.match(raw)
        if not m:
            continue
        key = m.group("key").upper()
        val = _unquote(m.group("val"))
        if key in ("WOODPECKER_AGENT_SECRET", "WOODPECKER_SERVER_SECRET", "WOODPECKER_SECRET"):
            secret_seen = True
            weak, reason = _is_weak(val)
            if weak:
                findings.append(
                    (i, f"{key}: {reason}")
                )
        elif key in ("WOODPECKER_HOST", "WOODPECKER_GRPC_ADDR", "WOODPECKER_SERVER"):
            if _host_is_remote(val):
                host_seen_remote = (i, key)
    if not secret_seen and host_seen_remote is not None:
        i, key = host_seen_remote
        findings.append(
            (i, f"{key} configured for non-local exposure but WOODPECKER_AGENT_SECRET is not set")
        )
    return findings


# ---- YAML (compose / helm values) -----------------------------------

YAML_KV = re.compile(
    r"""(?x)
    ^(?P<indent>\s*)
    (?:-\s+)?
    (?P<key>[A-Za-z_][A-Za-z0-9_.-]*)
    \s*:\s*
    (?P<val>.*?)\s*$
    """
)

# Handles `- WOODPECKER_AGENT_SECRET=foo` style inside a compose env
# list, plus `WOODPECKER_AGENT_SECRET: foo` style under environment:.
COMPOSE_ENVLIST = re.compile(
    r"""(?ix)
    ^\s*-\s*
    (?P<key>WOODPECKER_[A-Z0-9_]+)
    \s*=\s*
    (?P<val>"[^"]*"|'[^']*'|[^\s#]*)
    \s*(?:\#.*)?$
    """
)


def _scan_yaml(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    lines = source.splitlines()

    secret_seen = False
    host_seen_remote: Optional[Tuple[int, str]] = None
    has_agent_service = False

    # Pass 1 — helm-style nested keys: agent.secret / agent: { secret: ... }
    for i, raw in enumerate(lines, start=1):
        s = _strip_yaml_comment(raw)
        m = YAML_KV.match(s)
        if not m:
            continue
        key = m.group("key").lower()
        val = _unquote(m.group("val"))
        if val == "" or val.endswith(":"):
            continue
        # flat dotted helm form
        if key in ("agent.secret", "server.agent.secret", "agentsecret"):
            secret_seen = True
            weak, reason = _is_weak(val)
            if weak:
                findings.append((i, f"{key}: {reason}"))

    # Pass 2 — nested agent: \n  secret: ...
    for i, raw in enumerate(lines):
        s = _strip_yaml_comment(raw).rstrip()
        if re.match(r"^\s*agent\s*:\s*$", s):
            base = len(raw) - len(raw.lstrip(" "))
            j = i + 1
            while j < len(lines):
                rj = lines[j]
                if not rj.strip():
                    j += 1
                    continue
                ij = len(rj) - len(rj.lstrip(" "))
                if ij <= base:
                    break
                sj = _strip_yaml_comment(rj)
                mj = re.match(r"^\s*secret\s*:\s*(.*)$", sj)
                if mj:
                    val = _unquote(mj.group(1))
                    if val and not val.endswith(":"):
                        secret_seen = True
                        weak, reason = _is_weak(val)
                        if weak:
                            findings.append(
                                (j + 1, f"agent.secret: {reason}")
                            )
                j += 1

    # Pass 3 — compose-style environment lists & maps
    for i, raw in enumerate(lines, start=1):
        # list form: - KEY=val
        m = COMPOSE_ENVLIST.match(raw)
        if m:
            key = m.group("key").upper()
            val = _unquote(m.group("val"))
            if key in (
                "WOODPECKER_AGENT_SECRET",
                "WOODPECKER_SERVER_SECRET",
                "WOODPECKER_SECRET",
            ):
                secret_seen = True
                weak, reason = _is_weak(val)
                if weak:
                    findings.append((i, f"{key}: {reason}"))
            elif key in ("WOODPECKER_HOST", "WOODPECKER_GRPC_ADDR", "WOODPECKER_SERVER"):
                if _host_is_remote(val):
                    host_seen_remote = (i, key)
            continue
        # map form: KEY: val (under environment:)
        s = _strip_yaml_comment(raw)
        mk = re.match(
            r"^\s*(WOODPECKER_[A-Z0-9_]+)\s*:\s*(.*)$",
            s,
        )
        if mk:
            key = mk.group(1).upper()
            val = _unquote(mk.group(2))
            if val == "" or val.endswith(":"):
                # Treat empty RHS as the empty-secret case.
                if key in (
                    "WOODPECKER_AGENT_SECRET",
                    "WOODPECKER_SERVER_SECRET",
                    "WOODPECKER_SECRET",
                ):
                    secret_seen = True
                    findings.append(
                        (i, f"{key}: value is empty")
                    )
                continue
            if key in (
                "WOODPECKER_AGENT_SECRET",
                "WOODPECKER_SERVER_SECRET",
                "WOODPECKER_SECRET",
            ):
                secret_seen = True
                weak, reason = _is_weak(val)
                if weak:
                    findings.append((i, f"{key}: {reason}"))
            elif key in ("WOODPECKER_HOST", "WOODPECKER_GRPC_ADDR", "WOODPECKER_SERVER"):
                if _host_is_remote(val):
                    host_seen_remote = (i, key)

    # Service-name presence: woodpecker-agent / woodpeckerci/woodpecker-agent
    if re.search(r"(?im)^\s*woodpecker-agent\s*:\s*$", source) or re.search(
        r"woodpeckerci/woodpecker-agent", source
    ):
        has_agent_service = True

    if not secret_seen and (has_agent_service or host_seen_remote is not None):
        if host_seen_remote is not None:
            i, key = host_seen_remote
            findings.append(
                (i, f"{key} configured for non-local exposure but WOODPECKER_AGENT_SECRET is not set")
            )
        else:
            findings.append(
                (1, "woodpecker-agent service declared but WOODPECKER_AGENT_SECRET is not set anywhere in this file")
            )

    # de-dup
    return sorted({(l, r) for l, r in findings})


# ---- relevance gate + dispatch --------------------------------------


def _looks_relevant(source: str) -> bool:
    if "WOODPECKER_" in source:
        return True
    if re.search(r"(?im)^\s*woodpecker(-agent|-server)?\s*:\s*$", source):
        return True
    if "woodpeckerci/" in source:
        return True
    if re.search(r"(?im)^\s*agent\s*:\s*$", source) and "woodpecker" in source.lower():
        return True
    return False


def _classify(path: Path, source: str) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in (".yml", ".yaml"):
        return "yaml"
    if name.startswith(".env") or suffix in (".env", ".envfile", ".sh", ".bash", ".service", ".conf"):
        return "envish"
    # fall back: if it looks like an env file
    if re.search(r"(?m)^\s*WOODPECKER_[A-Z0-9_]+\s*=", source) and not re.search(
        r"(?m)^\s*[A-Za-z_][A-Za-z0-9_-]*\s*:\s", source
    ):
        return "envish"
    return "yaml"


def scan(source: str, path: Optional[Path] = None) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    if not _looks_relevant(source):
        return []
    p = path or Path("<stdin>")
    kind = _classify(p, source)
    if kind == "envish":
        return _scan_envfile(source)
    return _scan_yaml(source)


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in (
                "*.yml", "*.yaml",
                ".env", ".env.*",
                "*.env", "*.envfile",
                "*.service", "*.sh",
            ):
                targets.extend(sorted(path.rglob(pat)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source, f)
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

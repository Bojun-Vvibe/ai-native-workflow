#!/usr/bin/env python3
"""Detect NATS server config files that ship without any client
authorization configured while listening on a non-loopback interface.

NATS (``nats-server``) reads a HOCON-ish config that supports several
auth modes:

  * single-user:    ``authorization { user: ..., password: ... }``
  * multi-user:     ``authorization { users = [ {user: ..., password: ...} ] }``
  * token:          ``authorization { token: ... }``
  * NKey / JWT:     ``authorization { users = [ {nkey: ...} ] }`` /
                    operator + resolver mode
  * mTLS-with-cert-required: ``tls { verify: true }`` + ``tls { ca_file }``

If none of those are present and the server binds to ``0.0.0.0`` /
``::`` (or any non-loopback address, or omits ``host`` entirely which
defaults to all interfaces), any client on the network can publish /
subscribe to every subject and run ``$SYS`` admin requests when the
system account is left at its default.

LLM-generated ``nats-server.conf`` files commonly look like::

    port: 4222
    http_port: 8222
    # authorization stanza intentionally omitted

This detector flags those shapes.

What's checked (per file):
  - Listener binds to a non-loopback host (or ``host`` is absent).
  - There is no ``authorization { ... }`` block with at least one of:
    ``user`` + ``password``, ``token``, ``users = [...]``, or ``nkey``.
  - There is no ``operator`` / ``resolver`` directive (decentralized
    JWT auth mode).
  - mTLS with ``verify: true`` is treated as authentication.

Findings are reported per-line for the offending directive(s).

CWE refs:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-284: Improper Access Control
  - CWE-668: Exposure of Resource to Wrong Sphere

False-positive surface:
  - Embedded test harnesses on private docker networks. Suppress per
    file with a top comment ``# nats-no-auth-allowed`` anywhere in the
    file.
  - Listener bound only to ``127.0.0.1`` / ``::1`` / ``localhost`` is
    treated as safe.
  - ``no_auth_user`` set explicitly while an ``authorization`` block
    exists is left to the operator (we do warn separately).

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

SUPPRESS = re.compile(r"#\s*nats-no-auth-allowed")

HOST_RE = re.compile(r"^\s*(?:host|net)\s*[:=]\s*\"?([^\"\s,#}]+)\"?", re.IGNORECASE)
LISTEN_RE = re.compile(r"^\s*listen\s*[:=]\s*\"?([^\"\s,#}]+)\"?", re.IGNORECASE)
PORT_RE = re.compile(r"^\s*port\s*[:=]\s*(\d+)", re.IGNORECASE)

AUTHZ_OPEN_RE = re.compile(r"^\s*authorization\s*[:=]?\s*\{", re.IGNORECASE)
OPERATOR_RE = re.compile(r"^\s*operator\s*[:=]", re.IGNORECASE)
RESOLVER_RE = re.compile(r"^\s*resolver\s*[:=]", re.IGNORECASE)
ACCOUNTS_JWT_RE = re.compile(r"^\s*resolver_preload\s*[:=]?\s*\{", re.IGNORECASE)

TLS_OPEN_RE = re.compile(r"^\s*tls\s*[:=]?\s*\{", re.IGNORECASE)
TLS_VERIFY_TRUE_RE = re.compile(r"(?m)^\s*verify(?:_and_map)?\s*[:=]\s*true\b", re.IGNORECASE)

USER_KV_RE = re.compile(r"\b(user|username)\s*[:=]\s*\"?[^\"\s,}]+", re.IGNORECASE)
PASSWORD_KV_RE = re.compile(r"\bpass(?:word)?\s*[:=]\s*\"?[^\"\s,}]+", re.IGNORECASE)
TOKEN_KV_RE = re.compile(r"\btoken\s*[:=]\s*\"?[^\"\s,}]+", re.IGNORECASE)
USERS_LIST_RE = re.compile(r"\busers\s*[:=]?\s*\[", re.IGNORECASE)
NKEY_RE = re.compile(r"\bnkey\s*[:=]\s*\"?U[A-Z0-9]{20,}", re.IGNORECASE)

LOOPBACK = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}

WEAK_VALUES = {"", "''", '""', "changeme", "password", "secret", "admin"}


def _host_is_loopback(value: str) -> bool:
    # `listen` may be `host:port` form.
    if ":" in value and not value.startswith("["):
        host = value.rsplit(":", 1)[0]
    else:
        host = value
    host = host.strip("[]'\"")
    return host in LOOPBACK


def _block_text(lines: List[str], start: int) -> Tuple[str, int]:
    """Return the brace-balanced block beginning on ``lines[start]``
    (which must contain ``{``), plus the index of the line after it."""
    depth = 0
    chunks: List[str] = []
    for i in range(start, len(lines)):
        chunks.append(lines[i])
        depth += lines[i].count("{") - lines[i].count("}")
        if depth <= 0 and "}" in lines[i]:
            return "\n".join(chunks), i + 1
    return "\n".join(chunks), len(lines)


def _authz_block_has_real_auth(block: str) -> bool:
    has_token = bool(TOKEN_KV_RE.search(block))
    has_users_list = bool(USERS_LIST_RE.search(block))
    has_nkey = bool(NKEY_RE.search(block))
    has_user = bool(USER_KV_RE.search(block))
    has_pass = bool(PASSWORD_KV_RE.search(block))

    if has_token:
        # Reject empty / placeholder tokens.
        m = re.search(r"token\s*[:=]\s*\"?([^\"\s,}]+)", block, re.IGNORECASE)
        if m and m.group(1).strip("'\"").lower() not in WEAK_VALUES:
            return True
    if has_users_list:
        return True
    if has_nkey:
        return True
    if has_user and has_pass:
        m = re.search(r"pass(?:word)?\s*[:=]\s*\"?([^\"\s,}]+)", block, re.IGNORECASE)
        if m and m.group(1).strip("'\"").lower() not in WEAK_VALUES:
            return True
    return False


def _tls_block_requires_client_cert(block: str) -> bool:
    return bool(TLS_VERIFY_TRUE_RE.search(block))


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()

    has_explicit_host = False
    host_loopback = False
    host_line = 0
    host_value = ""

    has_port = False

    has_real_auth = False
    has_operator = False
    has_resolver = False
    tls_client_cert_required = False

    authz_seen_line = 0
    authz_empty = False

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.split("#", 1)[0]

        if not stripped.strip():
            i += 1
            continue

        if PORT_RE.match(stripped):
            has_port = True

        m = HOST_RE.match(stripped)
        if m:
            has_explicit_host = True
            host_line = i + 1
            host_value = m.group(1)
            host_loopback = _host_is_loopback(host_value)

        m = LISTEN_RE.match(stripped)
        if m:
            has_explicit_host = True
            has_port = True
            host_line = i + 1
            host_value = m.group(1)
            host_loopback = _host_is_loopback(host_value)

        if OPERATOR_RE.match(stripped):
            has_operator = True
        if RESOLVER_RE.match(stripped):
            has_resolver = True

        if AUTHZ_OPEN_RE.match(stripped):
            authz_seen_line = i + 1
            block, next_i = _block_text(lines, i)
            if _authz_block_has_real_auth(block):
                has_real_auth = True
            else:
                authz_empty = True
            i = next_i
            continue

        if TLS_OPEN_RE.match(stripped):
            block, next_i = _block_text(lines, i)
            if _tls_block_requires_client_cert(block):
                tls_client_cert_required = True
            i = next_i
            continue

        i += 1

    # If no port / listen, this isn't a server config we care about.
    if not has_port and not has_explicit_host:
        return findings

    bind_exposed = (not has_explicit_host) or (has_explicit_host and not host_loopback)
    auth_present = has_real_auth or (has_operator and has_resolver) or tls_client_cert_required

    if not bind_exposed:
        return findings

    if not auth_present:
        if authz_seen_line and authz_empty:
            findings.append((
                authz_seen_line,
                "authorization block present but defines no user/password/token/users/nkey",
            ))
        if has_explicit_host:
            findings.append((
                host_line,
                f"NATS listener binds non-loopback ({host_value}) without authorization / operator+resolver / mTLS verify",
            ))
        else:
            findings.append((
                1,
                "NATS listener has no host directive (defaults to all interfaces) without authorization",
            ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.conf", "nats-server.conf", "nats.conf"):
                targets.extend(sorted(path.rglob(ext)))
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

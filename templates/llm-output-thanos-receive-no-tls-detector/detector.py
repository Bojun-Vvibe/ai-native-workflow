#!/usr/bin/env python3
"""Detect Thanos Receive / Query / Sidecar configurations from LLM
output that disable TLS on the gRPC remote-write endpoint.

Thanos components accept a ``--grpc-server-tls-cert``,
``--grpc-server-tls-key``, ``--grpc-server-tls-client-ca`` family of
flags. When deploying ``thanos receive`` (which terminates Prometheus
remote-write traffic from many tenants) without those flags, every
sample on the wire is cleartext and any caller can write to any
tenant. LLMs frequently emit such configs because the "minimal
working" example in upstream README omits TLS.

This detector scans a config blob (raw text — argv, helm values YAML,
docker-compose snippet, systemd unit, k8s container args list) and
flags the unsafe shapes:

  1. A ``thanos receive`` invocation that exposes ``--grpc-address``
     on a non-loopback bind without any ``--grpc-server-tls-cert``.
  2. ``--grpc-server-tls-cert=""`` / ``--grpc-server-tls-cert=''``
     (explicit empty string defeating presence checks).
  3. ``--remote-write.config`` referencing ``http://`` (not https) for
     a non-loopback receive endpoint.
  4. Helm/YAML values: ``receive.grpc.tls.enabled: false`` while
     ``receive.service.type`` is ``LoadBalancer`` / ``NodePort``.

Suppression: a top-level comment ``# thanos-no-tls-allowed`` skips
the file (e.g. for local dev fixtures).

CWE-319 (Cleartext Transmission of Sensitive Information) and
CWE-306 (Missing Authentication for Critical Function) apply.

Public API:
    scan(text: str) -> list[tuple[int, str]]
        Returns a list of (line_number_1based, reason) tuples.
        Empty list = clean.

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*thanos-no-tls-allowed", re.IGNORECASE)

# Loopback / unspecified-but-private bind values we treat as safe.
LOOPBACK = {"127.0.0.1", "::1", "localhost", "[::1]"}

THANOS_RECEIVE = re.compile(r"\bthanos\s+receive\b")
GRPC_ADDR = re.compile(r"--grpc-address[=\s]+([^\s'\"]+)")
TLS_CERT = re.compile(r"--grpc-server-tls-cert[=\s]+([^\s]*)")
REMOTE_WRITE_URL = re.compile(r"--remote-write\.config[^\n]*?url:\s*([^\s'\"]+)")
HTTP_URL = re.compile(r"\bhttp://([^/\s'\"]+)")


def _bind_is_loopback(addr: str) -> bool:
    addr = addr.strip().strip("'\"")
    # strip port
    host = addr
    if host.startswith("["):
        # ipv6 with brackets
        end = host.find("]")
        if end > 0:
            host = host[1 : end]
    elif ":" in host and host.count(":") == 1:
        host = host.split(":", 1)[0]
    if host == "":
        return False
    return host in LOOPBACK


def _scan_cli_invocation(text: str, lines: List[str]) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if not THANOS_RECEIVE.search(text):
        return findings

    # Collect line index for each match for better reporting.
    invocation_line = 1
    for i, ln in enumerate(lines, start=1):
        if THANOS_RECEIVE.search(ln):
            invocation_line = i
            break

    addr_match = GRPC_ADDR.search(text)
    cert_match = TLS_CERT.search(text)

    bind_value = addr_match.group(1) if addr_match else "0.0.0.0:10901"
    cert_value = cert_match.group(1) if cert_match else None

    if not _bind_is_loopback(bind_value):
        if cert_value is None:
            findings.append(
                (
                    invocation_line,
                    f"thanos receive exposes --grpc-address={bind_value} "
                    f"without --grpc-server-tls-cert (cleartext gRPC remote-write)",
                )
            )
        else:
            cv = cert_value.strip().strip("'\"")
            if cv == "":
                # find that exact line for reporting
                cert_line = invocation_line
                for i, ln in enumerate(lines, start=1):
                    if "--grpc-server-tls-cert" in ln:
                        cert_line = i
                        break
                findings.append(
                    (
                        cert_line,
                        "--grpc-server-tls-cert is set to empty string (TLS effectively disabled)",
                    )
                )

    # Remote-write URL pointing at http:// (cleartext) for a
    # non-loopback host.
    for i, ln in enumerate(lines, start=1):
        m = HTTP_URL.search(ln)
        if not m:
            continue
        host = m.group(1).split(":")[0]
        if host in LOOPBACK:
            continue
        if "remote_write" in ln.lower() or "remotewrite" in ln.lower() or "remote-write" in ln.lower():
            findings.append(
                (
                    i,
                    f"remote-write target uses http:// scheme to non-loopback host {host}",
                )
            )

    return findings


def _scan_helm_values(lines: List[str]) -> List[Tuple[int, str]]:
    """Walk helm values-style YAML for the ``receive:`` sub-tree."""
    findings: List[Tuple[int, str]] = []
    in_receive = False
    receive_indent = -1
    tls_enabled: bool | None = None
    tls_enabled_line = 0
    svc_type = ""
    svc_type_line = 0

    for i, raw in enumerate(lines, start=1):
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))

        if re.match(r"^receive\s*:\s*$", stripped):
            in_receive = True
            receive_indent = indent
            continue

        if in_receive and indent <= receive_indent and stripped.strip():
            # left the receive: block
            in_receive = False

        if in_receive:
            m_tls = re.search(r"\btls\s*:\s*$", stripped)
            if m_tls:
                # peek for `enabled:` in following indented lines
                continue
            m_en = re.match(r"\s*enabled\s*:\s*(\S+)\s*$", stripped)
            if m_en and "tls" in "\n".join(lines[max(0, i - 4) : i]).lower():
                val = m_en.group(1).strip().lower().strip("'\"")
                if val == "false":
                    tls_enabled = False
                    tls_enabled_line = i
                elif val == "true":
                    tls_enabled = True
            m_svc = re.match(r"\s*type\s*:\s*(\S+)\s*$", stripped)
            if m_svc and "service" in "\n".join(lines[max(0, i - 4) : i]).lower():
                svc_type = m_svc.group(1).strip().strip("'\"")
                svc_type_line = i

    if tls_enabled is False and svc_type in {"LoadBalancer", "NodePort"}:
        findings.append(
            (
                tls_enabled_line,
                f"receive.tls.enabled=false while receive.service.type={svc_type} "
                f"(publicly reachable cleartext gRPC) — see line {svc_type_line}",
            )
        )
    return findings


def scan(text: str) -> List[Tuple[int, str]]:
    """Scan a config blob and return findings."""
    if SUPPRESS.search(text):
        return []
    lines = text.splitlines()
    findings: List[Tuple[int, str]] = []
    findings.extend(_scan_cli_invocation(text, lines))
    findings.extend(_scan_helm_values(lines))
    # de-dup while preserving order
    seen: set[Tuple[int, str]] = set()
    unique: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        unique.append(f)
    return unique


def _scan_path(p: Path) -> int:
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{p}:0:read-error: {exc}")
        return 0
    hits = scan(text)
    for line, reason in hits:
        print(f"{p}:{line}:{reason}")
    return 1 if hits else 0


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    n = 0
    for a in argv[1:]:
        n += _scan_path(Path(a))
    return min(255, n)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

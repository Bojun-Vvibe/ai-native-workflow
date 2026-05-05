#!/usr/bin/env python3
"""Detect CrowdSec configurations whose Local API (LAPI) is bound to
a public / wildcard interface without TLS, exposing the bouncer
enrollment + decision-push API to anyone reachable on the network.

Surfaces scanned:

* ``config.yaml`` — the LAPI ``api.server.listen_uri`` key. Wildcard
  binds (``0.0.0.0``, ``[::]``, ``::``, ``*``, missing host like
  ``:8080``) or explicit non-loopback IPv4 hosts are flagged unless
  an adjacent ``tls:`` block exists inside the same ``server:`` map.
* ``docker-compose.yml`` env block exporting ``LAPI_LISTEN_URI`` to
  a wildcard or non-loopback value.
* ``Dockerfile`` / shell invocations of ``crowdsec ... --listen-uri``
  with a wildcard or non-loopback value.

Suppression: a magic comment ``# crowdsec-lapi-listen-public-allowed``
on the same line or the line directly above silences the finding.

Stdlib-only. Exit code is the number of files with at least one
finding (capped at 255). Stdout lines: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*crowdsec-lapi-listen-public-allowed")

WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]", "*", ""}


def _is_loopback_host(host: str) -> bool:
    h = host.strip().strip("[]").lower()
    if h in {"localhost", "::1"}:
        return True
    if h.startswith("127."):
        return True
    return False


def _is_link_local_or_unspecified(host: str) -> bool:
    h = host.strip().strip("[]").lower()
    if h.startswith("169.254."):
        return True
    if h.startswith("fe80"):
        return True
    return False


def _classify_listen(value: str) -> Tuple[bool, str]:
    """Return (is_finding, reason) for a listen_uri / listen-uri value."""
    v = value.strip().strip('"').strip("'")
    if not v:
        return (
            True,
            "CrowdSec LAPI listen_uri is empty (binds wildcard by default)",
        )
    # Split host:port. IPv6 hosts are bracketed: [::]:8080
    host = ""
    if v.startswith("["):
        end = v.find("]")
        if end > 0:
            host = v[: end + 1]
        else:
            host = v
    else:
        if ":" in v:
            host = v.rsplit(":", 1)[0]
        else:
            host = v
    h_norm = host.strip()
    if h_norm in WILDCARD_HOSTS or h_norm.lower() in {"::", "[::]", "0.0.0.0"}:
        return (
            True,
            f"CrowdSec LAPI listen_uri {v!r} binds wildcard interface "
            "(public LAPI without scoped firewall)",
        )
    if _is_loopback_host(h_norm) or _is_link_local_or_unspecified(h_norm):
        return (False, "")
    # Any other explicit host: routable -> public surface.
    # IPv4 dotted-quad heuristic.
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", h_norm):
        return (
            True,
            f"CrowdSec LAPI listen_uri {v!r} binds non-loopback IPv4 host "
            "(public LAPI surface)",
        )
    return (False, "")


# api:
#   server:
#     listen_uri: 0.0.0.0:8080
LISTEN_URI_YAML = re.compile(
    r"""(?ix)
    ^(\s*)
    listen_uri
    \s*:\s*
    (?:"([^"]*)"|'([^']*)'|(\S+))
    \s*(?:\#.*)?$
    """
)


def _scan_config_yaml(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    lines = source.splitlines()
    # Track whether we are inside an api: > server: block, and whether
    # that server: block contains a tls: key.
    in_api = False
    in_server = False
    api_indent = -1
    server_indent = -1
    server_block_lines: List[Tuple[int, str]] = []
    server_has_tls = False
    server_listen_findings: List[Tuple[int, str]] = []

    def _flush_server() -> None:
        nonlocal server_listen_findings, server_has_tls
        if not server_has_tls:
            findings.extend(server_listen_findings)
        server_listen_findings = []
        server_has_tls = False

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        # Leaving previously-tracked blocks?
        if in_server and indent <= server_indent and stripped not in {""}:
            _flush_server()
            in_server = False
            server_indent = -1
        if in_api and indent <= api_indent and stripped not in {""}:
            in_api = False
            api_indent = -1

        if re.match(r"^api\s*:\s*$", stripped):
            in_api = True
            api_indent = indent
            continue
        if in_api and re.match(r"^server\s*:\s*$", stripped) and indent > api_indent:
            in_server = True
            server_indent = indent
            server_has_tls = False
            server_listen_findings = []
            continue
        if in_server:
            if re.match(r"^tls\s*:\s*$", stripped) and indent > server_indent:
                server_has_tls = True
            m = LISTEN_URI_YAML.match(raw)
            if m and indent > server_indent:
                value = m.group(2) if m.group(2) is not None else (
                    m.group(3) if m.group(3) is not None else (m.group(4) or "")
                )
                hit, reason = _classify_listen(value)
                if hit:
                    server_listen_findings.append((i, reason))

    if in_server:
        _flush_server()
    return findings


COMPOSE_ENV = re.compile(
    r"""(?ix)
    ^\s*-?\s*
    LAPI_LISTEN_URI
    \s*[:=]\s*
    (?:"([^"]*)"|'([^']*)'|(\S+))
    \s*(?:\#.*)?$
    """
)
CLI_FLAG = re.compile(
    r"""(?ix)
    --listen[-_]uri
    (?:
        [\s=]+ (?:"([^"\s]*)"|'([^'\s]*)'|(\S+))
      | "\s*,\s*"([^"]*)"            # JSON exec form: "--listen-uri", "0.0.0.0:8080"
      | '\s*,\s*'([^']*)'            # JSON exec form, single-quoted
    )
    """
)


def _scan_compose_or_dockerfile(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        m = COMPOSE_ENV.search(raw)
        if m:
            value = m.group(1) if m.group(1) is not None else (
                m.group(2) if m.group(2) is not None else (m.group(3) or "")
            )
            hit, reason = _classify_listen(value)
            if hit:
                findings.append(
                    (i, "LAPI_LISTEN_URI env: " + reason)
                )
            continue
        m = CLI_FLAG.search(raw)
        if m:
            value = next(
                (g for g in m.groups() if g is not None),
                "",
            )
            hit, reason = _classify_listen(value)
            if hit:
                findings.append(
                    (i, "crowdsec --listen-uri flag: " + reason)
                )
    return findings


def _filter_suppressed(
    lines: List[str], findings: List[Tuple[int, str]]
) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for ln, msg in findings:
        same = lines[ln - 1] if 0 < ln <= len(lines) else ""
        prev = lines[ln - 2] if ln - 2 >= 0 else ""
        if SUPPRESS.search(same) or SUPPRESS.search(prev):
            continue
        out.append((ln, msg))
    return out


def scan_file(path: Path) -> List[Tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    name = path.name.lower()
    suffix = path.suffix.lower()
    findings: List[Tuple[int, str]] = []
    if suffix in {".yml", ".yaml"}:
        # Could be either crowdsec config.yaml or docker-compose.
        findings.extend(_scan_config_yaml(text))
        if "compose" in name or "docker" in name:
            findings.extend(_scan_compose_or_dockerfile(text))
    if (
        "compose" in name
        or "dockerfile" in name
        or suffix == ".sh"
        or name.endswith(".envfile")
    ):
        findings.extend(_scan_compose_or_dockerfile(text))
    if not findings:
        # Best-effort fallback: try both scanners for unknown extensions.
        findings.extend(_scan_config_yaml(text))
        findings.extend(_scan_compose_or_dockerfile(text))
    # Deduplicate by (line, msg).
    seen = set()
    deduped: List[Tuple[int, str]] = []
    for ln, msg in findings:
        key = (ln, msg)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((ln, msg))
    return _filter_suppressed(text.splitlines(), deduped)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <file> [<file> ...]", file=sys.stderr)
        return 2
    files_with_findings = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.is_file():
            continue
        findings = scan_file(p)
        if not findings:
            continue
        files_with_findings += 1
        for ln, msg in findings:
            print(f"{p}:{ln}:{msg}")
    return min(files_with_findings, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

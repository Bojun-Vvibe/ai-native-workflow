#!/usr/bin/env python3
"""Detect ``dnsmasq`` configurations that act as an open recursive
resolver because none of the standard scoping directives is present.

A safe dnsmasq deployment scopes the listener with **at least one**
of:

* ``local-service`` — only answer queries from local subnets
* ``interface=<iface>`` — bind to a specific interface
* ``listen-address=<ip>`` — bind to specific addresses (must be
  non-wildcard; ``0.0.0.0`` / ``::`` does not count)
* ``bind-dynamic`` together with ``interface=`` (counted via
  ``interface=``)

If none is present, dnsmasq falls back to wildcard binding on every
interface and answers recursive queries for the whole internet —
useful as a DNS amplification reflector.

Surfaces scanned:

* ``dnsmasq.conf`` and any file under ``dnsmasq.d/``
* ``docker-compose.yml`` env / command lines that pass dnsmasq flags
* ``Dockerfile`` ``CMD`` / ``ENTRYPOINT`` invocations of ``dnsmasq``

Suppression: a magic comment ``# dnsmasq-no-local-service-allowed``
on the same line or directly above silences the finding.

Stdlib-only. Exit code is the number of files with at least one
finding (capped at 255). Stdout lines: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*dnsmasq-no-local-service-allowed")

LOCAL_SERVICE = re.compile(r"^\s*local-service\s*(?:#.*)?$", re.IGNORECASE)
INTERFACE_DIR = re.compile(r"^\s*interface\s*=\s*\S", re.IGNORECASE)
LISTEN_ADDR = re.compile(r"^\s*listen-address\s*=\s*([^\s#]+)", re.IGNORECASE)
DNSMASQ_CMDLINE = re.compile(r"\bdnsmasq(?:\b|$)", re.IGNORECASE)
WILDCARD = {"0.0.0.0", "::", "[::]"}


def _is_dnsmasq_config(text: str) -> bool:
    """Heuristic: does this look like a dnsmasq config file?"""
    keys = (
        "domain-needed", "bogus-priv", "no-resolv", "server=",
        "address=", "cache-size", "dhcp-range", "dhcp-host",
        "interface=", "listen-address=", "local-service",
        "no-dhcp-interface", "expand-hosts", "domain=", "log-queries",
    )
    hit = 0
    for k in keys:
        if k in text:
            hit += 1
            if hit >= 2:
                return True
    return False


def _scan_dnsmasq_conf(text: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    has_local_service = False
    has_interface = False
    has_specific_listen = False
    wildcard_listen_line = -1
    for i, raw in enumerate(text.splitlines(), start=1):
        if LOCAL_SERVICE.match(raw):
            has_local_service = True
        if INTERFACE_DIR.match(raw):
            has_interface = True
        m = LISTEN_ADDR.match(raw)
        if m:
            addrs = [a.strip() for a in m.group(1).split(",") if a.strip()]
            if any(a not in WILDCARD for a in addrs):
                has_specific_listen = True
            if any(a in WILDCARD for a in addrs):
                wildcard_listen_line = i
    if not (has_local_service or has_interface or has_specific_listen):
        ln = wildcard_listen_line if wildcard_listen_line > 0 else 1
        reason = (
            "dnsmasq config defines no local-service / interface= / "
            "non-wildcard listen-address= (open recursive resolver)"
        )
        findings.append((ln, reason))
    return findings


CMD_LOCAL_SERVICE = re.compile(r"--local-service\b", re.IGNORECASE)
CMD_INTERFACE = re.compile(r"--interface(?:=|\s+)\S", re.IGNORECASE)
CMD_LISTEN_ADDR = re.compile(
    r"--listen-address(?:=|\s+)([^\s\"',\]]+)", re.IGNORECASE
)


def _scan_command_lines(text: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if not DNSMASQ_CMDLINE.search(raw):
            continue
        # Skip lines that are clearly image references / pulls / labels,
        # not invocations.
        stripped = raw.strip()
        if re.match(r"^(image\s*:|FROM\s+|LABEL\s+|#|//)", stripped, re.IGNORECASE):
            continue
        if "/dnsmasq" in raw and "command" not in raw.lower() and "cmd" not in raw.lower() and "entrypoint" not in raw.lower() and not re.search(r"\bdnsmasq\s+-", raw):
            # path-like reference (image: foo/dnsmasq:tag, repo URL) -> skip
            continue
        # Require an actual flag or arg on the line so a bare mention
        # of the word doesn't trip.
        if not re.search(r"(?:\sdnsmasq\s+-|\"dnsmasq\"|'dnsmasq'|^dnsmasq\s+-|\bdnsmasq\s+(?:-[a-zA-Z]|--))", raw):
            continue
        if CMD_LOCAL_SERVICE.search(raw):
            continue
        if CMD_INTERFACE.search(raw):
            continue
        m = CMD_LISTEN_ADDR.search(raw)
        if m:
            addrs = [a.strip() for a in m.group(1).split(",") if a.strip()]
            if any(a not in WILDCARD for a in addrs):
                continue
        findings.append(
            (
                i,
                "dnsmasq invocation lacks --local-service / --interface= / "
                "non-wildcard --listen-address= (open recursive resolver)",
            )
        )
    return findings


def _filter_suppressed(
    lines: List[str], findings: List[Tuple[int, str]]
) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for ln, msg in findings:
        same = lines[ln - 1] if 0 < ln <= len(lines) else ""
        prev = lines[ln - 2] if ln - 2 >= 0 else ""
        # Also accept a top-of-file allow on line 1.
        top = lines[0] if lines else ""
        if SUPPRESS.search(same) or SUPPRESS.search(prev) or SUPPRESS.search(top):
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

    is_compose_or_docker = (
        suffix in {".yml", ".yaml"}
        or "compose" in name
        or "dockerfile" in name
        or suffix == ".dockerfile"
    )

    if is_compose_or_docker:
        findings.extend(_scan_command_lines(text))
    else:
        # Treat as dnsmasq config file if it looks like one or is named
        # dnsmasq.conf / lives under dnsmasq.d/.
        if (
            "dnsmasq" in name
            or suffix == ".conf"
            or _is_dnsmasq_config(text)
        ):
            findings.extend(_scan_dnsmasq_conf(text))
        # Also try cmdline scan in case the file mixes both.
        findings.extend(_scan_command_lines(text))

    # De-duplicate by (line, msg).
    seen = set()
    uniq: List[Tuple[int, str]] = []
    for ln, msg in findings:
        key = (ln, msg)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((ln, msg))

    return _filter_suppressed(text.splitlines(), uniq)


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

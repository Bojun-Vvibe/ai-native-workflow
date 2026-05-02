#!/usr/bin/env python3
"""Detect MongoDB ``mongod.conf`` files (or equivalent ``--bind_ip``
CLI snippets) that bind the daemon to all interfaces — i.e.
``bindIp: 0.0.0.0`` (or ``::``), or ``bindIpAll: true``.

Background. MongoDB 3.6+ ships with ``bindIp: 127.0.0.1`` by default
specifically because earlier versions, which bound to all interfaces,
were the source of the largest data-leak campaigns of 2017
("MongoDB ransom" sweeps). LLM-generated config files routinely
revert to the pre-3.6 behavior because the simplest "make it reachable
from another container" answer is to set ``bindIp: 0.0.0.0`` or
``bindIpAll: true`` — without addressing the *real* fix (private
network + auth + TLS).

This detector is intentionally orthogonal to "no auth" detectors. It
fires on the **listener exposure** misconfig regardless of whether
``security.authorization`` is also disabled — because exposing mongod
to all interfaces is a misconfig on its own (it expands blast radius,
breaks the principle of least exposure, and gates only on TLS / auth
layers that have historically been turned off accidentally).

What's checked (per file):
  - YAML ``net.bindIp`` whose value contains ``0.0.0.0`` or ``::`` /
    ``::0`` / ``[::]`` (with or without other IPs in the list).
  - YAML ``net.bindIpAll: true``.
  - INI / legacy ``bind_ip = 0.0.0.0`` (and ``bind_ip_all = true``).
  - ``mongod`` CLI fragments containing ``--bind_ip 0.0.0.0`` or
    ``--bind_ip_all``.

Findings are reported per-line.

CWE refs:
  - CWE-668: Exposure of Resource to Wrong Sphere
  - CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
  - CWE-1188: Initialization of a Resource with an Insecure Default

False-positive surface:
  - Suppress per file with a comment ``# mongodb-bind-all-allowed``
    anywhere in the file.
  - ``bindIp: 127.0.0.1`` (or any list of loopback-only addresses)
    is treated as safe.
  - ``bindIp: 0.0.0.0`` inside a Kubernetes Pod manifest is still
    flagged: clusters routinely expose Pod IPs and even host network
    pods, and a NetworkPolicy is not implied by the mongod config.

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

SUPPRESS = re.compile(r"#\s*mongodb-bind-all-allowed")

# YAML-style: under `net:` -> `bindIp: ...` or `bindIpAll: true`.
YAML_BINDIP_RE = re.compile(
    r"^(?P<indent>\s*)bindIp\s*:\s*(?P<val>.+?)\s*(?:#.*)?$",
    re.IGNORECASE,
)
YAML_BINDIPALL_RE = re.compile(
    r"^\s*bindIpAll\s*:\s*(true|yes|on)\b",
    re.IGNORECASE,
)

# Legacy INI: bind_ip = 0.0.0.0
INI_BINDIP_RE = re.compile(
    r"^\s*bind_ip\s*=\s*(?P<val>.+?)\s*(?:#.*)?$",
    re.IGNORECASE,
)
INI_BINDIPALL_RE = re.compile(
    r"^\s*bind_ip_all\s*=\s*(true|yes|on|1)\b",
    re.IGNORECASE,
)

# CLI fragments embedded in shell snippets / Dockerfiles / k8s args.
CLI_BINDIP_RE = re.compile(
    r"--bind[_-]?ip(?:\s+|=)([^\s\"']+)",
    re.IGNORECASE,
)
CLI_BINDIPALL_RE = re.compile(r"--bind[_-]?ip[_-]?all\b", re.IGNORECASE)

LOOPBACK = {"127.0.0.1", "::1", "localhost", "[::1]"}
ALL_INTERFACES = {"0.0.0.0", "::", "::0", "[::]", "[::0]", "*"}


def _split_addrs(value: str) -> List[str]:
    # Mongo accepts `bindIp: 0.0.0.0,127.0.0.1` (comma list, no quotes)
    # or YAML list `[0.0.0.0, 127.0.0.1]`.
    val = value.strip().strip("[]").strip("'\"")
    parts = re.split(r"[\s,]+", val)
    return [p.strip().strip("'\"") for p in parts if p.strip()]


def _addrs_contain_all(value: str) -> Tuple[bool, str]:
    addrs = _split_addrs(value)
    for a in addrs:
        if a in ALL_INTERFACES:
            return True, a
    return False, ""


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    for i, raw in enumerate(source.splitlines(), start=1):
        # Strip end-of-line comment for matching (but keep raw line no).
        line = raw

        m = YAML_BINDIP_RE.match(line)
        if m:
            hit, addr = _addrs_contain_all(m.group("val"))
            if hit:
                findings.append((
                    i,
                    f"net.bindIp includes all-interfaces address ({addr}) — "
                    f"mongod will accept connections from every reachable network",
                ))
            continue

        if YAML_BINDIPALL_RE.match(line):
            findings.append((
                i,
                "net.bindIpAll: true binds mongod to every interface",
            ))
            continue

        m = INI_BINDIP_RE.match(line)
        if m:
            hit, addr = _addrs_contain_all(m.group("val"))
            if hit:
                findings.append((
                    i,
                    f"legacy bind_ip = ... includes all-interfaces address ({addr})",
                ))
            continue

        if INI_BINDIPALL_RE.match(line):
            findings.append((
                i,
                "legacy bind_ip_all = true binds mongod to every interface",
            ))
            continue

        # CLI fragments — only on lines that look like a mongod
        # invocation, to avoid triggering on README prose. We just check
        # for the substring `mongod` on the same line.
        if "mongod" in line.lower():
            for m in CLI_BINDIP_RE.finditer(line):
                hit, addr = _addrs_contain_all(m.group(1))
                if hit:
                    findings.append((
                        i,
                        f"mongod --bind_ip includes all-interfaces address ({addr})",
                    ))
            if CLI_BINDIPALL_RE.search(line):
                findings.append((
                    i,
                    "mongod --bind_ip_all flag binds to every interface",
                ))

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("mongod.conf", "*.yaml", "*.yml", "*.conf", "*.sh", "Dockerfile"):
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

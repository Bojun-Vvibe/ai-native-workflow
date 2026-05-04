#!/usr/bin/env python3
"""Detect Apache Airflow ``airflow.cfg`` configurations that leave the
stable REST API behind ``airflow.api.auth.backend.default`` (no-op
auth) while the web server is reachable on a non-loopback host.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import configparser
import io
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"^\s*#\s*airflow-auth-allowed\s*$", re.MULTILINE)
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}
DEFAULT_BACKEND = "airflow.api.auth.backend.default"


def _line_of(source: str, needle: str) -> int:
    idx = source.find(needle)
    if idx < 0:
        return 1
    return source.count("\n", 0, idx) + 1


def _parse(source: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.read_file(io.StringIO(source))
    return cp


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    try:
        cp = _parse(source)
    except configparser.Error:
        return findings

    if not cp.has_section("api"):
        return findings

    backend_singular = (cp.get("api", "auth_backend", fallback="") or "").strip()
    backend_plural = (cp.get("api", "auth_backends", fallback="") or "").strip()
    backends_listed = [
        b.strip() for b in re.split(r"[,\s]+", backend_plural) if b.strip()
    ]
    if backend_singular:
        backends_listed.append(backend_singular)

    if DEFAULT_BACKEND not in backends_listed:
        return findings
    # If the operator explicitly stacked a real backend alongside the
    # default one (rare but possible), still flag — Airflow uses
    # first-success semantics and the default backend always succeeds.

    host = (cp.get("webserver", "web_server_host", fallback="") or "").strip()
    if host and host in LOOPBACK_HOSTS:
        return findings

    enable_exp = (
        cp.get("api", "enable_experimental_api", fallback="False").strip().lower()
        == "true"
    )

    needle = "auth_backends" if backend_plural else "auth_backend"
    line = _line_of(source, needle)
    bind_desc = host if host else "<all interfaces>"
    reasons = [
        f"api.{needle} contains {DEFAULT_BACKEND} (no-op auth) on "
        f"webserver bind={bind_desc}",
    ]
    if enable_exp:
        reasons.append(
            "api.enable_experimental_api=True — legacy /api/experimental/ is "
            "also exposed without auth"
        )
    if not backend_plural:
        reasons.append(
            "no auth_backends list configured — relying solely on the legacy "
            "singular setting"
        )
    findings.append((line, "; ".join(reasons)))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            targets.extend(sorted(path.rglob("airflow.cfg")))
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

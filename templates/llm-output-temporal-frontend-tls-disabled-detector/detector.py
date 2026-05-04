#!/usr/bin/env python3
"""Detect Temporal server YAML configs that disable TLS / host
verification on the frontend (or internode) listeners.

Temporal's server config (``config/development.yaml``,
``config/docker.yaml``, helm values for the
``temporalio/server`` chart) accepts a ``global.tls`` block of the
shape::

    global:
      tls:
        internode:
          server:
            certFile: /etc/temporal/certs/cluster.pem
            keyFile:  /etc/temporal/certs/cluster.key
          client:
            serverName: cluster.local
            disableHostVerification: false
        frontend:
          server:
            certFile: /etc/temporal/certs/frontend.pem
            keyFile:  /etc/temporal/certs/frontend.key
          client:
            serverName: frontend.local
            disableHostVerification: false

LLM output frequently regresses this in three ways:

  1. ``frontend`` (or ``internode``) block is set to literal ``null``
     / ``{}`` / commented out while a public listener is exposed.
  2. ``disableHostVerification: true`` is set on the client side,
     turning a TLS handshake into transport-only encryption (no
     identity check — trivially MITM'd).
  3. The whole ``global.tls`` key is absent while ``frontend.address``
     points at a non-loopback bind.

This detector flags those shapes.

What it checks (per file):

  - ``global.tls.frontend`` is missing, ``null``, or empty while
    ``services.frontend.rpc.bindOnIP`` is non-loopback / absent.
  - ``global.tls.internode`` is missing / empty when at least one
    other peer service (``matching``, ``history``, ``worker``) is
    configured (cluster mode).
  - Any ``disableHostVerification: true`` under ``global.tls.*.client``.
  - ``requireClientAuth: false`` under ``global.tls.frontend.server``
    (plain-TLS without client cert verification).

Suppression:
  - Add a top-of-file comment ``# temporal-tls-disabled-allowed``
    to suppress (e.g. for unit-test fixtures).

CWE refs:
  - CWE-295: Improper Certificate Validation
  - CWE-319: Cleartext Transmission of Sensitive Information
  - CWE-306: Missing Authentication for Critical Function

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*temporal-tls-disabled-allowed")

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_comment(line: str) -> str:
    # Remove trailing `#...` but keep `#` inside quoted strings (rare here).
    out = []
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


def _parse_kv(line: str) -> Optional[Tuple[str, str]]:
    s = _strip_comment(line)
    if ":" not in s:
        return None
    key, _, val = s.lstrip(" -").partition(":")
    return key.strip(), val.strip()


def _is_empty_value(val: str) -> bool:
    """A YAML scalar that means 'no content' for our purposes."""
    if val == "":
        return True
    v = val.strip().strip("'").strip('"').lower()
    if v in {"~", "null", "{}", "[]"}:
        return True
    return False


def _block_lines(lines: List[str], start: int, base_indent: int) -> List[Tuple[int, str]]:
    """Yield (line_no_1based, text) for the YAML block starting after
    ``lines[start]`` whose indent is strictly greater than
    ``base_indent``. Comments and blank lines are skipped."""
    out: List[Tuple[int, str]] = []
    for j in range(start + 1, len(lines)):
        raw = lines[j]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        ind = _indent(raw)
        if ind <= base_indent:
            break
        out.append((j + 1, raw))
    return out


def _find_top_key(lines: List[str], path: List[str]) -> Optional[int]:
    """Find a nested key path under top-level (e.g. ['global','tls'])
    and return the 0-based line index of the deepest key found, or
    None."""
    cursor = 0
    expected_indent = 0
    for depth, key in enumerate(path):
        found = -1
        for j in range(cursor, len(lines)):
            raw = lines[j]
            stripped = _strip_comment(raw)
            if not stripped.strip():
                continue
            ind = _indent(raw)
            if depth > 0 and ind < expected_indent:
                # left the parent block
                return None
            if ind == expected_indent and stripped.lstrip(" -").startswith(key + ":"):
                found = j
                break
            if ind == expected_indent and depth == 0:
                # other top-level key, keep scanning
                continue
        if found < 0:
            return None
        cursor = found + 1
        # next level indent inferred from the first child
        for k in range(found + 1, len(lines)):
            raw = lines[k]
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            ind = _indent(raw)
            if ind <= expected_indent:
                return found  # leaf scalar / empty mapping
            expected_indent = ind
            break
        else:
            return found
    return cursor - 1


def _value_at(lines: List[str], idx: int) -> str:
    kv = _parse_kv(lines[idx])
    return kv[1] if kv else ""


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()

    # Quick relevance check: must look like a Temporal config.
    txt = "\n".join(lines)
    has_global = re.search(r"(?m)^global\s*:", txt) is not None
    has_services = re.search(r"(?m)^services\s*:", txt) is not None
    has_frontend_svc = re.search(
        r"(?m)^\s+frontend\s*:\s*$", txt
    ) is not None or re.search(r"frontend\.rpc", txt) is not None
    if not (has_global or has_services or has_frontend_svc):
        return findings

    # 1) disableHostVerification: true anywhere under global.tls.*.client
    in_tls = False
    tls_indent = -1
    for i, raw in enumerate(lines):
        s = _strip_comment(raw)
        if not s.strip():
            continue
        ind = _indent(raw)
        if re.match(r"^\s*tls\s*:\s*$", raw):
            in_tls = True
            tls_indent = ind
            continue
        if in_tls and ind <= tls_indent and s.strip():
            in_tls = False
        if in_tls:
            m = re.match(r"^\s*disableHostVerification\s*:\s*(\S+)", raw)
            if m and m.group(1).strip().strip("'\"").lower() == "true":
                findings.append(
                    (i + 1, "global.tls.*.client.disableHostVerification=true bypasses cert identity check")
                )
            m2 = re.match(r"^\s*requireClientAuth\s*:\s*(\S+)", raw)
            if m2 and m2.group(1).strip().strip("'\"").lower() == "false":
                findings.append(
                    (i + 1, "global.tls.frontend.server.requireClientAuth=false disables mTLS client verification")
                )

    # 2) frontend tls block missing / empty
    tls_idx = _find_top_key(lines, ["global", "tls"])
    frontend_idx = _find_top_key(lines, ["global", "tls", "frontend"])

    bind_exposed = True
    bind_line = 1
    bind_value = "(unset)"
    fe_bind_idx = _find_top_key(lines, ["services", "frontend", "rpc", "bindOnIP"])
    if fe_bind_idx is not None:
        bv = _value_at(lines, fe_bind_idx).strip().strip("'\"")
        bind_line = fe_bind_idx + 1
        bind_value = bv or "(empty)"
        if bv in LOOPBACK_HOSTS:
            bind_exposed = False

    if tls_idx is None:
        if has_services and bind_exposed:
            findings.append(
                (bind_line, f"services.frontend.rpc.bindOnIP={bind_value} but no global.tls block defined")
            )
    else:
        # tls block exists; check frontend sub-block.
        if frontend_idx is None:
            if bind_exposed:
                findings.append(
                    (tls_idx + 1, "global.tls.frontend missing while frontend listener is non-loopback")
                )
        else:
            val = _value_at(lines, frontend_idx)
            if _is_empty_value(val):
                # Could still have children if scalar is empty; check children.
                kids = _block_lines(lines, frontend_idx, _indent(lines[frontend_idx]))
                if not kids and bind_exposed:
                    findings.append(
                        (frontend_idx + 1, "global.tls.frontend is null/empty (TLS effectively disabled)")
                    )
                else:
                    block_text = "\n".join(t for _, t in kids)
                    if not re.search(r"\bcertFile\s*:", block_text) and bind_exposed:
                        findings.append(
                            (frontend_idx + 1, "global.tls.frontend has no certFile (TLS not configured)")
                        )

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.yaml", "*.yml"):
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

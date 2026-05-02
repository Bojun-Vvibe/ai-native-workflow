#!/usr/bin/env python3
"""Detect ``mlflow server`` / ``mlflow ui`` invocations bound to a
non-loopback interface without the basic-auth app enabled.

Scans shell scripts, Dockerfiles, docker-compose YAML, systemd unit
files, and Kubernetes pod/deployment specs for ``mlflow server`` /
``mlflow ui`` command lines.

Suppression: any file containing ``# mlflow-auth-external`` is
skipped.

CWE refs: CWE-306, CWE-284.

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

SUPPRESS = re.compile(r"#\s*mlflow-auth-external")

# Match `mlflow server` or `mlflow ui` anywhere on a line. We
# deliberately allow ``/`` and other path chars before ``mlflow`` so
# absolute-path invocations (``/usr/local/bin/mlflow server``) match.
MLFLOW_CMD_RE = re.compile(
    r"""
    (?:^|[\s'"\[,/])
    mlflow
    [\s'"\],]+
    (?P<sub>server|ui)
    \b
    (?P<rest>[^\n]*)
    """,
    re.VERBOSE,
)

HOST_FLAG_RE = re.compile(
    r"""(?:--host[=\s'",\]]+|(?:^|[\s'",\[])-h[\s'",\]]+)['"]?([^\s'"\\,\]]+)""",
    re.IGNORECASE,
)

APP_BASIC_AUTH_RE = re.compile(
    r"""--app[-_]name[=\s'",\]]+['"]?basic[-_]auth['"]?""",
    re.IGNORECASE,
)
# Also allow a generic --app-name <plugin> as long as plugin != "default".
APP_NAME_RE = re.compile(
    r"""--app[-_]name[=\s'",\]]+['"]?([A-Za-z0-9._-]+)['"]?""",
    re.IGNORECASE,
)

LOOPBACK = {"127.0.0.1", "::1", "localhost"}

# File globs we will scan in directory mode.
FILE_GLOBS = (
    "*.sh",
    "*.bash",
    "*.zsh",
    "*.yml",
    "*.yaml",
    "*.service",
    "Dockerfile",
    "Dockerfile.*",
    "*.dockerfile",
    "*.conf",
)


def _logical_lines(source: str) -> List[Tuple[int, str]]:
    """Join shell line continuations (``\\`` at end) and YAML block-scalar
    indented continuations into single logical lines. Preserves the
    **starting** line number of each logical line.

    YAML detection is intentionally heuristic: when a line ends with
    ``>`` or ``|`` (optionally with chomping indicators ``-`` / ``+``),
    we absorb subsequent lines whose indent is strictly greater than
    the parent's, until we hit a less-indented line.
    """
    raw_lines = source.splitlines()
    out: List[Tuple[int, str]] = []
    i = 0
    n = len(raw_lines)
    while i < n:
        raw = raw_lines[i]
        # YAML block scalar: a line ending with `: >` or `: |` (with
        # optional `-`/`+` chomping). Absorb following deeper-indented
        # lines.
        block_match = re.match(r"^(\s*).*[:\-]\s*[>|][-+]?\s*$", raw)
        if block_match:
            base_indent = len(re.match(r"^\s*", raw).group(0))
            start = i + 1
            buf = [raw]
            j = i + 1
            while j < n:
                nxt = raw_lines[j]
                if not nxt.strip():
                    j += 1
                    continue
                indent = len(re.match(r"^\s*", nxt).group(0))
                if indent > base_indent:
                    buf.append(nxt.strip())
                    j += 1
                else:
                    break
            out.append((start, " ".join(buf)))
            i = j
            continue

        # Shell line continuation.
        if raw.rstrip().endswith("\\"):
            start = i + 1
            buf = [raw.rstrip()[:-1]]
            j = i + 1
            while j < n:
                nxt = raw_lines[j]
                if buf and buf[-1].endswith("\\"):
                    buf[-1] = buf[-1][:-1]
                if nxt.rstrip().endswith("\\"):
                    buf.append(nxt.rstrip()[:-1])
                    j += 1
                    continue
                buf.append(nxt.rstrip())
                j += 1
                break
            out.append((start, " ".join(buf)))
            i = j
            continue

        out.append((i + 1, raw))
        i += 1
    return out


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    for lineno, line in _logical_lines(source):
        m = MLFLOW_CMD_RE.search(line)
        if not m:
            continue

        rest = m.group("rest")
        sub = m.group("sub")
        # Determine host.
        host_match = HOST_FLAG_RE.search(rest)
        host = host_match.group(1) if host_match else None

        # Determine auth.
        has_basic_auth = bool(APP_BASIC_AUTH_RE.search(rest))
        app_name_match = APP_NAME_RE.search(rest)
        has_custom_app = bool(
            app_name_match
            and app_name_match.group(1).lower() not in {"default", "basic"}
        )
        # We only treat basic-auth (or any non-default app) as auth.
        # For our purposes, basic-auth is the canonical gate.
        auth_present = has_basic_auth or has_custom_app

        if host is None:
            # No --host flag. In file types where this almost always
            # means "all interfaces" (Dockerfile CMD/ENTRYPOINT, systemd
            # ExecStart, k8s container args/command), flag it.
            looks_container = (
                "CMD " in line
                or line.strip().startswith("CMD")
                or "ENTRYPOINT" in line
                or "ExecStart=" in line
                or "command:" in line
                or "args:" in line
                or line.strip().startswith("- ")
            )
            if looks_container and not auth_present:
                findings.append((
                    lineno,
                    f"mlflow {sub} CMD without --host (defaults to all interfaces) and no --app-name basic-auth",
                ))
            continue

        host_clean = host.strip("'\"")
        if host_clean in LOOPBACK:
            continue

        if not auth_present:
            findings.append((
                lineno,
                f"mlflow {sub} bound to non-loopback (host={host_clean}) without --app-name basic-auth",
            ))

    return findings


def _iter_targets(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            seen: set = set()
            for pat in FILE_GLOBS:
                for cand in sorted(path.rglob(pat)):
                    if cand in seen:
                        continue
                    seen.add(cand)
                    yield cand
        else:
            yield path


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for f in _iter_targets(paths):
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
    return min(255, scan_paths([Path(a) for a in argv[1:]]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

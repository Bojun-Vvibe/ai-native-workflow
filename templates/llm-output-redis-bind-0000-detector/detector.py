#!/usr/bin/env python3
"""Detect Redis ``redis.conf`` files that bind to all network interfaces
via ``bind 0.0.0.0`` (or ``::``) — i.e. exposing Redis to every reachable
network — without an authentication mechanism (no ``requirepass``, and
``protected-mode no``).

Redis ships with ``bind 127.0.0.1 -::1`` and ``protected-mode yes`` so a
fresh install only listens on loopback. LLM-generated configs routinely
"fix the can't-connect-from-app-server" problem by setting
``bind 0.0.0.0`` and turning protected-mode off, accidentally publishing
an unauthenticated Redis to the network. Combined with no
``requirepass``, this is one of the most-exploited misconfigurations on
the public internet.

What's checked (per file):
  - ``bind`` directive containing ``0.0.0.0`` / ``::`` / ``*``.
  - ``protected-mode no`` is captured to escalate the bind-all finding
    to "bind-all + protected-mode off".
  - ``requirepass`` presence is captured to downgrade the finding to
    info-only when set to a non-empty value.

CWE refs:
  - CWE-668: Exposure of Resource to Wrong Sphere
  - CWE-306: Missing Authentication for Critical Function
  - CWE-1188: Initialization of a Resource with an Insecure Default

False-positive surface:
  - Containerized Redis on a private overlay network where the host is
    genuinely isolated. Suppress per file with a comment
    ``# redis-bind-all-allowed`` anywhere in the file.
  - ``bind 127.0.0.1`` / ``bind ::1`` / specific non-wildcard IPs are
    treated as safe.
  - ``requirepass <non-empty>`` downgrades the bind-all finding to
    info-only (no exit code impact) unless ``protected-mode no`` is
    also present.

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

SUPPRESS = re.compile(r"#\s*redis-bind-all-allowed")

# ``bind <addr> [<addr> ...] [-::1]``  — values are space-separated.
BIND_RE = re.compile(r"^\s*bind\s+(?P<vals>[^#\n]+?)\s*(?:#.*)?$", re.IGNORECASE)
PROTECTED_NO_RE = re.compile(r"^\s*protected-mode\s+no\b", re.IGNORECASE)
PROTECTED_YES_RE = re.compile(r"^\s*protected-mode\s+yes\b", re.IGNORECASE)
REQUIREPASS_RE = re.compile(
    r"""^\s*requirepass\s+(?P<val>['"]?[^#\n]+?['"]?)\s*(?:#.*)?$""",
    re.IGNORECASE,
)

WILDCARDS = {"0.0.0.0", "::", "*"}


def _tokens(values: str) -> List[str]:
    out: List[str] = []
    for tok in values.split():
        # Strip leading "-" used by Redis to mark "optional" addresses
        # (e.g. ``bind 127.0.0.1 -::1``).
        if tok.startswith("-"):
            tok = tok[1:]
        tok = tok.strip("'\"")
        if tok:
            out.append(tok)
    return out


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    bind_line = 0
    bind_value = ""
    bind_is_wildcard = False

    protected_no_line = 0
    protected_yes = False

    requirepass_set = False

    for i, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        m = BIND_RE.match(raw)
        if m:
            toks = _tokens(m.group("vals"))
            for tok in toks:
                if tok in WILDCARDS:
                    bind_line = i
                    bind_value = tok
                    bind_is_wildcard = True
                    break
            continue

        if PROTECTED_NO_RE.match(raw):
            protected_no_line = i
            continue
        if PROTECTED_YES_RE.match(raw):
            protected_yes = True
            continue

        rp = REQUIREPASS_RE.match(raw)
        if rp:
            val = rp.group("val").strip().strip("'\"")
            if val and val.lower() != "foobared":  # default placeholder
                requirepass_set = True
            continue

    if bind_is_wildcard:
        if protected_no_line and not requirepass_set:
            findings.append((
                bind_line,
                f"bind {bind_value} (all interfaces) AND protected-mode no on line "
                f"{protected_no_line} with no requirepass — Redis fully exposed without auth",
            ))
        elif protected_no_line:
            findings.append((
                bind_line,
                f"bind {bind_value} (all interfaces) AND protected-mode no on line "
                f"{protected_no_line} — protection disabled, password must be strong",
            ))
        elif not requirepass_set and not protected_yes:
            findings.append((
                bind_line,
                f"bind {bind_value} binds Redis to all interfaces with no requirepass "
                f"and no explicit protected-mode yes — likely public exposure",
            ))
        elif not requirepass_set and protected_yes:
            # Listening on all interfaces but protected-mode yes will
            # block unauthenticated connections from non-loopback. Note
            # but do not raise: this is only safe by accident.
            pass
        # If requirepass_set and protected_yes/absent, info-only.

    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("redis.conf", "*.redis.conf"):
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

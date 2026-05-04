#!/usr/bin/env python3
"""Detect ScyllaDB ``scylla.yaml`` snippets (or rendered docs / compose /
k8s manifests) that leave authentication or authorization fully open via
the ``AllowAll*`` family of plugins.

Scylla is wire-compatible with Cassandra and ships the same insecure
defaults: ``authenticator: AllowAllAuthenticator`` and
``authorizer: AllowAllAuthorizer``. LLMs frequently reproduce these
defaults verbatim when asked "give me a scylla.yaml" or "deploy scylla
on kubernetes", which yields a cluster where any client that can reach
port 9042 can read or modify every keyspace.

Rules:

  1. ``authenticator: AllowAllAuthenticator`` (uncommented)
  2. ``authorizer:   AllowAllAuthorizer``    (uncommented)
  3. CLI/env variant: ``--authenticator=AllowAllAuthenticator`` or
     ``SCYLLA_AUTHENTICATOR=AllowAllAuthenticator`` / authorizer equiv.
  4. ``broadcast_rpc_address: 0.0.0.0`` (or any non-loopback) **plus**
     any ``AllowAll*`` line in the same file - cluster is reachable
     from anywhere with no auth.

Suppression: a top-level ``# scylla-public-readonly-ok`` comment in the
file disables all rules (intentional public sandbox).

Public API:
    detect(text: str) -> bool
    scan(text: str)   -> list[(line, reason)]

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "scylla-public-readonly-ok"

# Match key: value forms (yaml) or --key=value / KEY=value forms (cli/env).
_AUTHENTICATOR_RE = re.compile(
    r"""(?ix)
    (?:^|\s|["'=])
    (?:--)?
    (?:scylla[_-])?
    authenticator
    \s*[:=]\s*
    ["']?
    AllowAllAuthenticator
    ["']?
    """,
    re.MULTILINE,
)

_AUTHORIZER_RE = re.compile(
    r"""(?ix)
    (?:^|\s|["'=])
    (?:--)?
    (?:scylla[_-])?
    authorizer
    \s*[:=]\s*
    ["']?
    AllowAllAuthorizer
    ["']?
    """,
    re.MULTILINE,
)

_BROADCAST_RE = re.compile(
    r"""(?im)
    ^\s*
    (?:broadcast_rpc_address|rpc_address|broadcast_address|listen_address)
    \s*:\s*
    ["']?
    (?P<addr>[0-9a-fA-F:.]+)
    ["']?
    \s*$
    """,
    re.VERBOSE,
)


def _is_loopback(addr: str) -> bool:
    a = addr.strip().strip("\"'").lower()
    if a in {"127.0.0.1", "::1", "localhost"}:
        return True
    if a.startswith("127."):
        return True
    return False


def _strip_comments(text: str) -> str:
    """Remove yaml/shell ``#`` comments so commented-out warnings don't
    trigger. Preserve newlines for accurate line numbers."""
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            # Replace with blank line to preserve numbering
            nl = "\n" if line.endswith("\n") else ""
            out.append(nl)
            continue
        # Inline comment: only if # is preceded by whitespace
        idx = -1
        in_quote = None
        for i, ch in enumerate(line):
            if in_quote:
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in "\"'":
                in_quote = ch
                continue
            if ch == "#" and (i == 0 or line[i - 1].isspace()):
                idx = i
                break
        if idx >= 0:
            tail = "\n" if line.endswith("\n") else ""
            out.append(line[:idx].rstrip() + tail)
        else:
            out.append(line)
    return "".join(out)


def scan(text: str) -> list[tuple[int, str]]:
    if SUPPRESS in text:
        return []

    cleaned = _strip_comments(text)
    findings: list[tuple[int, str]] = []

    def line_of(pos: int) -> int:
        return cleaned.count("\n", 0, pos) + 1

    has_allowall = False
    for m in _AUTHENTICATOR_RE.finditer(cleaned):
        findings.append(
            (line_of(m.start()), "authenticator set to AllowAllAuthenticator (no login required)")
        )
        has_allowall = True
    for m in _AUTHORIZER_RE.finditer(cleaned):
        findings.append(
            (line_of(m.start()), "authorizer set to AllowAllAuthorizer (every user has every permission)")
        )
        has_allowall = True

    if has_allowall:
        for m in _BROADCAST_RE.finditer(cleaned):
            addr = m.group("addr")
            if not _is_loopback(addr):
                findings.append(
                    (
                        line_of(m.start()),
                        f"non-loopback bind {addr!r} combined with AllowAll* auth - cluster is open to network",
                    )
                )

    findings.sort(key=lambda t: t[0])
    return findings


def detect(text: str) -> bool:
    return bool(scan(text))


def _cli(argv: list[str]) -> int:
    if not argv:
        text = sys.stdin.read()
        hits = scan(text)
        for ln, reason in hits:
            print(f"<stdin>:{ln}: {reason}")
        return 1 if hits else 0

    files_with_hits = 0
    for arg in argv:
        p = Path(arg)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            print(f"{arg}: cannot read: {e}", file=sys.stderr)
            files_with_hits += 1
            continue
        hits = scan(text)
        if hits:
            files_with_hits += 1
            for ln, reason in hits:
                print(f"{arg}:{ln}: {reason}")
    return files_with_hits


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))

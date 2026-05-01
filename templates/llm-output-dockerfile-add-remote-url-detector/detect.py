#!/usr/bin/env python3
"""
llm-output-dockerfile-add-remote-url-detector

Flags Dockerfiles that use `ADD <http(s)|ftp)://...>` to pull a remote
artifact directly into the image. This is the documented anti-pattern
called out by Docker's own best-practices guide and maps to CWE-494
(Download of Code Without Integrity Check): the remote payload is
fetched at build time over the network, expanded into the image, and
no checksum is verified. LLMs reach for `ADD <url>` because it looks
shorter than `RUN curl -fsSL ... && sha256sum -c`.

We only flag the `ADD` form (which is the dangerous-by-default one).
`RUN curl ...` is out of scope here -- a separate detector covers
shell-pipe-to-shell. We also accept multi-line continuations (trailing
backslash) and inline comments.

Stdlib only. Reads files passed on argv (or recurses into dirs and
picks files named `Dockerfile`, `*.Dockerfile`, or `Dockerfile.*`).
Exit 0 = no findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# Remote schemes that ADD will fetch over the network.
_REMOTE_SCHEME = re.compile(
    r"\b(?:https?|ftp)://[^\s\"']+",
    re.IGNORECASE,
)

# Match `ADD` instruction at start of a logical line (leading whitespace ok),
# case-insensitive per Dockerfile rules. We do NOT match COPY -- COPY
# rejects URLs at parse time.
_ADD_RE = re.compile(r"^\s*ADD\b", re.IGNORECASE)


def _logical_lines(text: str) -> Iterable[Tuple[int, str]]:
    """Yield (1-based starting line number, joined logical line) honoring
    Dockerfile backslash continuations. Strips trailing inline comments
    only when the line starts with `#`; in-instruction `#` is data."""
    raw = text.splitlines()
    i = 0
    n = len(raw)
    while i < n:
        start_lineno = i + 1
        line = raw[i]
        # Skip pure comment / blank lines.
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        # Join continuations.
        joined_parts = [line.rstrip()]
        while joined_parts[-1].endswith("\\") and i + 1 < n:
            joined_parts[-1] = joined_parts[-1][:-1]  # drop trailing \
            i += 1
            joined_parts.append(raw[i].rstrip())
        i += 1
        yield start_lineno, " ".join(p.strip() for p in joined_parts).strip()


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, logical in _logical_lines(text):
        if not _ADD_RE.match(logical):
            continue
        # Tokenize after ADD; first token may be --chown=... / --checksum=...
        # We just look for any remote URL in the source list.
        # Note: ADD has form `ADD [--flags] <src>... <dest>` so URL is in srcs.
        m = _REMOTE_SCHEME.search(logical)
        if not m:
            continue
        # If --checksum= is present, treat as integrity-checked and skip.
        # (Docker added this in BuildKit; if the LLM bothered, give credit.)
        if re.search(r"--checksum=\S+", logical):
            continue
        url = m.group(0)
        findings.append(
            f"{path}:{lineno}: ADD with remote URL and no --checksum= "
            f"(CWE-494, fetched at build time without integrity check): "
            f"url={url}"
        )
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    base = f
                    if (
                        base == "Dockerfile"
                        or base.endswith(".Dockerfile")
                        or base.startswith("Dockerfile.")
                        or base.endswith(".dockerfile")
                    ):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

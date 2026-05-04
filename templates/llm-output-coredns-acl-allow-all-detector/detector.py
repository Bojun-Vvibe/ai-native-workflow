#!/usr/bin/env python3
"""Detect CoreDNS Corefile configurations whose ``acl`` plugin grants
unrestricted query access to the world (``allow net 0.0.0.0/0`` or
``allow net ::/0``) on a public listener — a shape that LLM-generated
"just expose CoreDNS" snippets ship verbatim and that turns the
resolver into an open recursive resolver suitable for DNS amplification
attacks.

Rules: a finding is emitted for any *server block* that

* binds the resolver to a public scheme (``.:53``, ``dns://.:53``,
  ``tls://.:853``, etc., where the host portion is empty / ``.`` /
  ``0.0.0.0`` / ``::``) AND
* contains an ``acl`` plugin whose policy block has at least one
  ``allow net 0.0.0.0/0`` or ``allow net ::/0`` directive (or simply
  ``allow net 0.0.0.0/0 ::/0`` on one line) AND
* does NOT immediately follow that with a tighter ``block net`` /
  ``filter net`` rule that excludes the world.

A magic comment ``# coredns-public-resolver-allowed`` anywhere in the
file suppresses the finding.

Stdlib-only. Exit code is the count of files with at least one finding
(capped at 255). Stdout lines have the form ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*coredns-public-resolver-allowed")

# A server block header: one or more zone/scheme tokens followed by '{'.
# Examples: ".:53 {", "dns://.:53 {", "tls://.:853 example.com {".
HEADER_RE = re.compile(r"^([^\{#\n]+?)\{\s*(?:#.*)?$")
ACL_OPEN_RE = re.compile(r"^\s*acl\b[^\{#\n]*\{\s*(?:#.*)?$", re.IGNORECASE)
ALLOW_ALL_V4 = re.compile(r"\b0\.0\.0\.0/0\b")
ALLOW_ALL_V6 = re.compile(r"::/0\b")
BLOCK_RE = re.compile(r"^\s*(?:block|filter)\s+net\b", re.IGNORECASE)
ALLOW_RE = re.compile(r"^\s*allow\s+net\b", re.IGNORECASE)

PUBLIC_HOST_TOKENS = {"", ".", "0.0.0.0", "::", "[::]"}


def _tokenize_zones(header: str) -> List[str]:
    return [t for t in header.strip().split() if t]


def _zone_is_public(zone: str) -> bool:
    """Return True if the zone token binds to all interfaces.

    A CoreDNS zone token looks like ``[scheme://]host[:port]`` where
    ``host`` may be a domain name, an IP, or empty/``.``. We treat the
    block as public-bound when the host portion is empty, ``.``,
    ``0.0.0.0``, or ``::``.
    """
    body = zone
    if "://" in body:
        body = body.split("://", 1)[1]
    # Strip trailing port (handle bracketed IPv6).
    if body.startswith("["):
        # [::]:53 or [::1]:53
        end = body.find("]")
        if end == -1:
            host = body
        else:
            host = body[1:end]
    else:
        if ":" in body:
            host, _ = body.rsplit(":", 1)
        else:
            host = body
    return host in PUBLIC_HOST_TOKENS


def _block_is_public(zone_tokens: List[str]) -> bool:
    # CoreDNS routes a query to a server block if any zone token
    # matches. The block is "public" iff at least one of its zones
    # listens on a public host.
    return any(_zone_is_public(z) for z in zone_tokens)


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    lines = source.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped.strip():
            i += 1
            continue
        m = HEADER_RE.match(stripped)
        # Heuristic: only treat as a server-block header when the line
        # ends with '{' AND the previous non-empty context is at depth
        # 0. We track depth explicitly below.
        if m and stripped.rstrip().endswith("{"):
            zones = _tokenize_zones(m.group(1))
            header_line = i + 1
            # Walk the block body, tracking nested braces.
            depth = 1
            j = i + 1
            acl_blocks: List[Tuple[int, List[str]]] = []
            while j < len(lines) and depth > 0:
                body_raw = lines[j]
                body = body_raw.split("#", 1)[0]
                if ACL_OPEN_RE.match(body):
                    acl_start = j + 1
                    depth += 1
                    inner = []
                    k = j + 1
                    inner_depth = 1
                    while k < len(lines) and inner_depth > 0:
                        kbody = lines[k].split("#", 1)[0]
                        opens = kbody.count("{")
                        closes = kbody.count("}")
                        inner_depth += opens - closes
                        if inner_depth <= 0:
                            depth -= 1
                            break
                        inner.append(kbody)
                        k += 1
                    acl_blocks.append((acl_start, inner))
                    j = k + 1
                    continue
                opens = body.count("{")
                closes = body.count("}")
                depth += opens - closes
                j += 1

            if _block_is_public(zones):
                for acl_line, body_lines in acl_blocks:
                    has_allow_all = False
                    has_block_all = False
                    allow_line = acl_line
                    for off, bl in enumerate(body_lines):
                        if ALLOW_RE.match(bl) and (
                            ALLOW_ALL_V4.search(bl) or ALLOW_ALL_V6.search(bl)
                        ):
                            has_allow_all = True
                            allow_line = acl_line + off
                        if BLOCK_RE.match(bl) and (
                            ALLOW_ALL_V4.search(bl) or ALLOW_ALL_V6.search(bl)
                        ):
                            has_block_all = True
                    if has_allow_all and not has_block_all:
                        findings.append((
                            allow_line,
                            (
                                "CoreDNS server block "
                                f"{' '.join(zones)} on a public listener has "
                                "acl plugin with 'allow net 0.0.0.0/0' "
                                "(or ::/0) and no offsetting block/filter — "
                                "open recursive resolver"
                            ),
                        ))
            i = j
            continue
        i += 1
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("Corefile", "*.corefile", "*Corefile*", "*.conf"):
                targets.extend(sorted(path.rglob(pat)))
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

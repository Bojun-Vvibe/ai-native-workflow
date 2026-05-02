#!/usr/bin/env python3
"""
llm-output-haproxy-stats-no-auth-detector

Flags HAProxy configurations that **enable the stats interface
without authentication**. The stats page leaks backend / frontend
topology, server health, request rates, sticky-table contents, and
- when `stats admin` is set - exposes admin actions (enable/disable
backends) to anonymous callers.

Pattern flagged:

  * A `listen <name>` / `frontend <name>` / `backend <name>` block
    that contains `stats enable` (or `stats uri ...`) but does NOT
    contain a `stats auth user:pass` line within the same block.

  * A bare `stats socket ... mode 666` (world-writable runtime API).

  * `stats admin if TRUE` (admin actions allowed unconditionally).

References
----------
- HAProxy docs, "Statistics page", `stats auth` directive.
- CWE-306: Missing Authentication for Critical Function.
- CWE-732: Incorrect Permission Assignment for Critical Resource.
- OWASP A05:2021 Security Misconfiguration.

Why LLMs ship this
------------------
Quickstart / blog snippets routinely show:
    listen stats
        bind *:8404
        stats enable
        stats uri /
to illustrate the page, then get pasted verbatim into prod configs
without `stats auth` ever being added.

Stdlib only. Scans `*.cfg`, `*.conf`, `haproxy.cfg`, plus generic
`.txt` / `.yaml` / `.yml` files (in case configs are inlined into
ConfigMaps / Helm values).

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_BLOCK_HEADER = re.compile(
    r"""^\s*(listen|frontend|backend|defaults)\b\s*([^\s#]*)""",
    re.IGNORECASE,
)
_STATS_ENABLE = re.compile(r"""^\s*stats\s+enable\b""", re.IGNORECASE)
_STATS_URI = re.compile(r"""^\s*stats\s+uri\b""", re.IGNORECASE)
_STATS_AUTH = re.compile(
    r"""^\s*stats\s+auth\s+\S+:\S+""", re.IGNORECASE,
)
_STATS_HTTP_AUTH = re.compile(
    r"""^\s*stats\s+http-request\s+auth""", re.IGNORECASE,
)
_STATS_ADMIN_TRUE = re.compile(
    r"""^\s*stats\s+admin\s+if\s+(?:TRUE|true|1)\b""", re.IGNORECASE,
)
_STATS_SOCKET_MODE = re.compile(
    r"""^\s*stats\s+socket\b.*\bmode\s+(\d{3,4})""", re.IGNORECASE,
)
_COMMENT = re.compile(r"""^\s*#""")


def _iter_blocks(lines: List[str]) -> Iterable[Tuple[str, int, int]]:
    """Yield (header_text, start_line_idx, end_line_idx_exclusive)."""
    starts: List[Tuple[int, str]] = []
    for i, raw in enumerate(lines):
        if _COMMENT.match(raw) or raw.strip() == "":
            continue
        m = _BLOCK_HEADER.match(raw)
        if m:
            starts.append((i, raw.rstrip()))
    starts.append((len(lines), ""))
    for idx in range(len(starts) - 1):
        s, hdr = starts[idx]
        e, _ = starts[idx + 1]
        yield hdr, s, e


def scan_haproxy(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()

    # Per-block: stats enable / uri without stats auth.
    for hdr, s, e in _iter_blocks(lines):
        block = lines[s:e]
        has_enable = False
        has_uri = False
        has_auth = False
        has_http_auth = False
        admin_true_line = -1
        enable_line = -1
        for offset, raw in enumerate(block):
            if _COMMENT.match(raw):
                continue
            if _STATS_ENABLE.match(raw):
                has_enable = True
                enable_line = s + offset + 1
            if _STATS_URI.match(raw):
                has_uri = True
                if enable_line < 0:
                    enable_line = s + offset + 1
            if _STATS_AUTH.match(raw):
                has_auth = True
            if _STATS_HTTP_AUTH.match(raw):
                has_http_auth = True
            if _STATS_ADMIN_TRUE.match(raw):
                admin_true_line = s + offset + 1
        if (has_enable or has_uri) and not (has_auth or has_http_auth):
            findings.append(
                f"{path}:{enable_line}: HAProxy block "
                f"`{hdr.strip()}` exposes stats page "
                f"({'enable' if has_enable else 'uri'}) without "
                f"`stats auth user:pass` -> anonymous access to "
                f"backend topology / health (CWE-306)"
            )
        if admin_true_line > 0 and not (has_auth or has_http_auth):
            findings.append(
                f"{path}:{admin_true_line}: HAProxy `stats admin if "
                f"TRUE` in block `{hdr.strip()}` allows anonymous "
                f"admin actions (CWE-306/CWE-732)"
            )

    # Global: world-writable runtime stats socket.
    for i, raw in enumerate(lines, start=1):
        if _COMMENT.match(raw):
            continue
        m = _STATS_SOCKET_MODE.search(raw)
        if m:
            mode = m.group(1)
            try:
                # Last digit = "other" perms; >=6 means write for world.
                if int(mode[-1]) >= 6:
                    findings.append(
                        f"{path}:{i}: HAProxy `stats socket ... mode "
                        f"{mode}` is world-writable -> any local user "
                        f"can drive the runtime API (CWE-732): "
                        f"{raw.strip()[:160]}"
                    )
            except ValueError:
                pass
    return findings


_TARGET_EXTS = (".cfg", ".conf", ".txt", ".yaml", ".yml")
_TARGET_BASENAMES = ("haproxy.cfg", "haproxy.conf")


def _is_target(path: str) -> bool:
    low = path.lower()
    base = os.path.basename(low)
    if base in _TARGET_BASENAMES:
        return True
    if base.startswith("haproxy") and low.endswith((".cfg", ".conf")):
        return True
    return low.endswith(_TARGET_EXTS)


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    if not _is_target(path):
        return []
    # Cheap pre-filter: skip unrelated yaml/txt with no haproxy keywords.
    low = path.lower()
    if low.endswith((".yaml", ".yml", ".txt")) \
            and "stats" not in text.lower() \
            and "haproxy" not in text.lower():
        return []
    return scan_haproxy(text, path)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    p = os.path.join(dp, f)
                    if _is_target(p):
                        yield p
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        for line in scan(path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

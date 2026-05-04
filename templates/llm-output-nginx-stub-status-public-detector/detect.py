#!/usr/bin/env python3
"""
llm-output-nginx-stub-status-public-detector

Flags nginx config blocks that enable `stub_status` (the
ngx_http_stub_status_module endpoint) without restricting access
via `allow`/`deny` ACLs or `auth_basic` / mTLS gating.

The `stub_status` endpoint exposes:
  - Active connections
  - Total accepted / handled / requests counters
  - Reading / writing / waiting state counts

When reachable from the public internet it leaks operational
telemetry that is useful for capacity planning attacks, side-channel
inference, and target reconnaissance. Combined with the default
`server_name _;` catch-all, it ends up reachable on every vhost.

Maps to:
  - CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
  - CWE-419: Unprotected Primary Channel
  - CWE-668: Exposure of Resource to Wrong Sphere
  - OWASP A01:2021 Broken Access Control

Why LLMs ship this
------------------
The official nginx docs and almost every "monitoring with nginx +
prometheus-nginx-exporter" tutorial show:

    location /nginx_status {
        stub_status;
    }

without any `allow 127.0.0.1; deny all;` lines. Models copy the
snippet verbatim into reverse-proxy configs that are then exposed
on `:80` / `:443`.

Heuristic
---------
We parse nginx-style config text and find any `location` block
whose body contains a `stub_status` directive. Inside that block
we look for at least one of:

  - `allow <not-public-cidr>;` followed by `deny all;`
  - `deny all;` (with no preceding `allow 0.0.0.0/0;`)
  - `auth_basic "<realm>";`
  - `auth_request <uri>;`
  - `satisfy any;` paired with one of the above
  - `internal;`     (only reachable via X-Accel-Redirect)

If none of those guards is present in the same `location` block,
we flag.

We also flag explicit anti-patterns inside the block:
  - `allow all;`
  - `allow 0.0.0.0/0;`
  - `allow ::/0;`

Out of scope (false-negative by design):
  - Access control inferred from a wrapping `if` block.
  - mTLS enforced at server level via `ssl_verify_client on;` —
    we do not climb the parse tree to the parent `server` block
    in this version.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_TARGET_NAMES = ("nginx.conf",)
_TARGET_EXTS = (".conf", ".nginx", ".cfg", ".include", ".vhost", ".snippet")

_COMMENT = re.compile(r"#.*$")
_LOCATION_OPEN = re.compile(
    r"""\blocation\b[^{]*\{""", re.IGNORECASE
)


def _strip_comments(text: str) -> str:
    out_lines = []
    for raw in text.splitlines():
        out_lines.append(_COMMENT.sub("", raw))
    return "\n".join(out_lines)


def _find_location_blocks(text: str) -> List[Tuple[int, int, int]]:
    """Return list of (start_offset, end_offset, start_line) tuples
    for top-level `location ... { ... }` blocks. Brace-balanced."""
    results: List[Tuple[int, int, int]] = []
    i = 0
    n = len(text)
    # Pre-compute a line-number mapping by counting newlines lazily.
    while i < n:
        m = _LOCATION_OPEN.search(text, i)
        if not m:
            break
        start = m.start()
        brace = m.end() - 1  # position of `{`
        depth = 1
        j = brace + 1
        while j < n and depth > 0:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            j += 1
        if depth != 0:
            break  # unbalanced, give up
        end = j
        start_line = text.count("\n", 0, start) + 1
        results.append((start, end, start_line))
        i = end
    return results


_STUB_STATUS = re.compile(r"""\bstub_status\b\s*(?:on)?\s*;""", re.IGNORECASE)
_DENY_ALL = re.compile(r"""\bdeny\s+all\s*;""", re.IGNORECASE)
_ALLOW_ALL = re.compile(
    r"""\ballow\s+(?:all|0\.0\.0\.0/0|::/0)\s*;""", re.IGNORECASE
)
_ALLOW_ANY = re.compile(r"""\ballow\s+\S+\s*;""", re.IGNORECASE)
_AUTH_BASIC = re.compile(r"""\bauth_basic\b[^;]*;""", re.IGNORECASE)
_AUTH_REQUEST = re.compile(r"""\bauth_request\b[^;]*;""", re.IGNORECASE)
_INTERNAL = re.compile(r"""\binternal\s*;""", re.IGNORECASE)


def _has_guard(body: str) -> bool:
    if _AUTH_BASIC.search(body):
        # auth_basic "off"; is a sentinel that *disables* basic auth.
        for m in _AUTH_BASIC.finditer(body):
            inside = m.group(0).lower()
            if '"off"' in inside or "'off'" in inside or " off" in inside:
                continue
            return True
    if _AUTH_REQUEST.search(body):
        return True
    if _INTERNAL.search(body):
        return True
    if _DENY_ALL.search(body):
        # deny all; alone (or paired with allow <specific>;) is a
        # guard. allow all; followed by deny all; would still be
        # caught by the explicit anti-pattern check below.
        return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    cleaned = _strip_comments(text)
    for start, end, start_line in _find_location_blocks(cleaned):
        block = cleaned[start:end]
        if not _STUB_STATUS.search(block):
            continue
        # Explicit public-allow anti-pattern always flags.
        bad_allow = _ALLOW_ALL.search(block)
        if bad_allow:
            findings.append(
                f"{path}:{start_line}: nginx stub_status location "
                f"contains `allow all;` / `allow 0.0.0.0/0;` -> "
                f"server stats reachable from any network "
                f"(CWE-200/CWE-419)"
            )
            continue
        if not _has_guard(block):
            findings.append(
                f"{path}:{start_line}: nginx stub_status location "
                f"has no allow/deny ACL, auth_basic, auth_request, "
                f"or `internal;` guard -> server stats reachable "
                f"from any network (CWE-200/CWE-419)"
            )
    return findings


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    return scan_text(text, path)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
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

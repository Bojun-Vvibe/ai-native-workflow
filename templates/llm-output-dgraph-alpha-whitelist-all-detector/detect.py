#!/usr/bin/env python3
"""
llm-output-dgraph-alpha-whitelist-all-detector

Flags Dgraph `alpha` deployments that whitelist 0.0.0.0/0 (or
equivalent all-nets blocks) for the **admin / mutation** endpoints.

Dgraph's alpha node ships an admin GraphQL endpoint at `/admin` that
exposes destructive mutations (drop_all, drop_data, backup, restore,
shutdown, login, change password, export). Access is gated by a
`security` flag with two sub-options:

    --security "whitelist=<CIDR list>;token=<shared token>"

If `whitelist` includes `0.0.0.0/0`, `0.0.0.0`, `0.0.0.0/1`, or any
unbounded prefix that covers the public internet, AND no ACL token
is configured, the admin surface is reachable from anywhere.

Maps to:
  - CWE-284: Improper Access Control
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-285: Improper Authorization
  - OWASP A01:2021 Broken Access Control

Why LLMs ship this
------------------
The Dgraph quickstart in the official tutorial uses
`--security "whitelist=0.0.0.0/0"` to make the admin endpoint
reachable from a developer laptop without setting up TLS / ACLs.
The model copies the quickstart into a "production" docker-compose
or k8s manifest.

Heuristic
---------
We look for the option in CLI / Dockerfile / docker-compose / k8s
args / systemd forms:

    --security "whitelist=0.0.0.0/0;..."
    --security whitelist=0.0.0.0/0
    --security=whitelist=0.0.0.0/0
    -security "whitelist=0.0.0.0/0"   (single-dash form, also accepted by Dgraph)

A whitelist value is flagged if it contains any of:
  - 0.0.0.0/0
  - 0.0.0.0/1
  - 0.0.0.0    (bare, no mask -> Dgraph treats as /0)
  - ::/0       (IPv6 catch-all)

We do NOT flag:
  - whitelist with bounded private CIDRs (10.0.0.0/8, 192.168.0.0/16,
    172.16.0.0/12, 100.64.0.0/10, 127.0.0.0/8, fc00::/7, fe80::/10,
    169.254.0.0/16),
  - --security with only a token=... and no whitelist=,
  - comments / docs that mention the bad option.

If a `token=` sub-option is also present alongside an all-nets
whitelist, we still flag (token alone does not make 0.0.0.0/0 safe;
admin endpoints should be network-restricted regardless).

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Match `--security ...` / `-security ...` / `--security=...`.
# We capture the value (which may be quoted and contain `;`).
_SECURITY_FLAG = re.compile(
    r"""(?P<flag>--?security)(?:\s*=\s*|\s+)(?P<val>"[^"]*"|'[^']*'|\S+)""",
    re.IGNORECASE,
)

_OPEN_NETS = (
    "0.0.0.0/0",
    "0.0.0.0/1",
    "::/0",
)

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _strip_shell_comment(line: str) -> str:
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
    return "".join(out)


def _value_unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _whitelist_subvalue(val: str) -> str | None:
    """Extract whitelist=... sub-value from a --security argument."""
    parts = re.split(r"[;,]", val)
    for p in parts:
        kv = p.strip().split("=", 1)
        if len(kv) == 2 and kv[0].strip().lower() == "whitelist":
            return kv[1].strip()
    return None


def _is_open(whitelist_val: str) -> bool:
    # Dgraph accepts comma- or whitespace-separated CIDR list in the
    # whitelist value.
    tokens = re.split(r"[,\s]+", whitelist_val.strip())
    for t in tokens:
        t = t.strip().strip('"').strip("'")
        if not t:
            continue
        if t in _OPEN_NETS:
            return True
        # Bare 0.0.0.0 (no mask) -> Dgraph treats as /0.
        if t == "0.0.0.0":
            return True
    return False


# Standalone whitelist=<value> token (value may be quoted; stops at
# `;`, end-quote, or whitespace).
_BARE_WHITELIST = re.compile(
    r"""\bwhitelist\s*=\s*(?P<v>"[^"]*"|'[^']*'|[^;\s,"'\]]+)""",
    re.IGNORECASE,
)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        # Form 1: --security <value> with whitelist= sub-option in
        # the same value.
        hit_on_line = False
        for m in _SECURITY_FLAG.finditer(line):
            val = _value_unquote(m.group("val"))
            wl = _whitelist_subvalue(val)
            if wl is None:
                continue
            if _is_open(wl):
                findings.append(
                    f"{path}:{lineno}: dgraph alpha --security "
                    f"whitelist includes 0.0.0.0/0 (or equivalent) -> "
                    f"admin endpoint reachable from any network "
                    f"(CWE-284/CWE-732): {raw.strip()[:200]}"
                )
                hit_on_line = True
        if hit_on_line:
            continue
        # Form 2: bare `whitelist=<open-net>` on its own line / token
        # (multi-line YAML array, JSON array element, etc.).
        for m in _BARE_WHITELIST.finditer(line):
            wl_val = _value_unquote(m.group("v"))
            # Reuse `_is_open` semantics over a single-or-list value.
            if _is_open(wl_val):
                findings.append(
                    f"{path}:{lineno}: dgraph alpha whitelist=... "
                    f"includes 0.0.0.0/0 (or equivalent) -> admin "
                    f"endpoint reachable from any network "
                    f"(CWE-284/CWE-732): {raw.strip()[:200]}"
                )
    return findings


_TARGET_NAMES = ("dockerfile", "docker-compose.yml", "docker-compose.yaml")
_TARGET_EXTS = (".yaml", ".yml", ".sh", ".bash", ".service",
                ".dockerfile", ".envfile", ".conf", ".cfg")


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
                    if low in _TARGET_NAMES \
                            or low.startswith("dockerfile") \
                            or low.startswith("docker-compose"):
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
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

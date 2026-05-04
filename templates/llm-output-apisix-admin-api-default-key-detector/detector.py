#!/usr/bin/env python3
"""Detect Apache APISIX ``config.yaml`` files that ship the upstream
default ``admin_key`` value while the Admin API listens on a
non-loopback interface.

The well-known default key ``edd1c9f034335f136f87ad84b625c8f1`` (and
its viewer counterpart ``4054f7cf07e344346cd3f287985e76a2``) appear in
the upstream ``config-default.yaml`` and in countless tutorials. With
that key in place, anyone able to reach the Admin API on
``9180``/``9443`` can register routes, change upstreams, or load Lua
plugins — i.e. full data-plane RCE.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"^\s*#\s*apisix-default-key-allowed\s*$", re.MULTILINE)

DEFAULT_KEYS = {
    "edd1c9f034335f136f87ad84b625c8f1",  # admin role
    "4054f7cf07e344346cd3f287985e76a2",  # viewer role
}

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}

# Match `key: <value>` (quoted or bare) inside the admin_key list.
KEY_LINE = re.compile(
    r"""^\s*-?\s*key\s*:\s*['"]?([0-9a-fA-F]{16,64})['"]?\s*(?:\#.*)?$""",
    re.MULTILINE,
)

# Match a top-level allow_admin entry (a YAML list under `deployment.admin`
# or `apisix.admin_api`); we look for any non-loopback CIDR.
ALLOW_ADMIN_BLOCK = re.compile(
    r"^\s*allow_admin\s*:\s*(?P<body>(?:\n\s+-\s.+)+)",
    re.MULTILINE,
)
ALLOW_LIST_ITEM = re.compile(r"^\s*-\s*['\"]?([^'\"\n#]+?)['\"]?\s*(?:\#.*)?$", re.MULTILINE)

# Top-level admin listen IP (apisix.admin_listen.ip / deployment.admin.admin_listen.ip).
LISTEN_IP = re.compile(
    r"^\s*ip\s*:\s*['\"]?([0-9a-fA-F\.:]+)['\"]?\s*(?:\#.*)?$",
    re.MULTILINE,
)


def _line_of(source: str, needle_offset: int) -> int:
    return source.count("\n", 0, needle_offset) + 1


def _is_loopback_only(allow_items: List[str]) -> bool:
    """Return True iff every CIDR/IP in allow_admin maps to loopback."""
    if not allow_items:
        return False
    for item in allow_items:
        item = item.strip()
        if not item:
            continue
        # Strip /NN suffix.
        host = item.split("/", 1)[0]
        if host in LOOPBACK_HOSTS:
            continue
        if host.startswith("127."):
            continue
        return False
    return True


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    # Find all `key:` lines whose value matches a known default key.
    default_hits: List[Tuple[int, str]] = []
    for m in KEY_LINE.finditer(source):
        val = m.group(1).lower()
        if val in DEFAULT_KEYS:
            default_hits.append((_line_of(source, m.start()), val))
    if not default_hits:
        return findings

    # Determine listen exposure. We treat a non-loopback admin_listen ip
    # OR a non-loopback allow_admin entry as "exposed".
    exposed = False
    bind_desc = "<default 0.0.0.0>"
    for m in LISTEN_IP.finditer(source):
        ip = m.group(1).strip()
        if ip in LOOPBACK_HOSTS or ip.startswith("127."):
            bind_desc = ip
            # only counts as loopback if there is no broader allow_admin
        else:
            exposed = True
            bind_desc = ip
            break

    allow_items: List[str] = []
    am = ALLOW_ADMIN_BLOCK.search(source)
    if am:
        for li in ALLOW_LIST_ITEM.finditer(am.group("body")):
            allow_items.append(li.group(1))
        if not _is_loopback_only(allow_items):
            exposed = True
            bind_desc = f"allow_admin={allow_items}"
    else:
        # No allow_admin override: APISIX defaults to 0.0.0.0/0.
        if not exposed and bind_desc == "<default 0.0.0.0>":
            exposed = True

    if not exposed:
        return findings

    for line, val in default_hits:
        role = "admin" if val == "edd1c9f034335f136f87ad84b625c8f1" else "viewer"
        findings.append(
            (
                line,
                f"deployment.admin.admin_key uses upstream default {role} "
                f"key {val} on Admin API bind={bind_desc}",
            )
        )
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for name in ("config.yaml", "config.yml"):
                targets.extend(sorted(path.rglob(name)))
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

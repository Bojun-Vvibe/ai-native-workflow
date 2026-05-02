#!/usr/bin/env python3
"""Detect docker-compose YAML files that grant a service host-level
or near-host-level privileges by setting any of:

* ``privileged: true``                 — full host capabilities
* ``cap_add: [ALL]``                   — equivalent to privileged
* ``security_opt: [seccomp:unconfined]`` /
  ``[apparmor:unconfined]`` /
  ``[no-new-privileges:false]``        — disables kernel filters
* ``pid: host`` / ``pid: "host"``      — share host PID namespace
* ``ipc: host``                        — share host IPC namespace
* ``network_mode: host``               — share host network stack
* ``userns_mode: host``                — opt out of user-ns remap

Background
----------
``privileged: true`` in a Compose service is the docker-compose
equivalent of ``docker run --privileged`` — the container gets
~all kernel capabilities, all device nodes, and (depending on the
runtime) effectively becomes a thin wrapper around the host kernel.
A compromise of any process inside such a container is
indistinguishable from a compromise of the host. Each of the other
patterns above achieves a similar escape vector by a different
route (capabilities, kernel filter bypass, namespace sharing).

LLMs emit these patterns frequently because the most common
StackOverflow answer for "docker container can't access /dev/...",
"my container can't ping", or "FUSE doesn't work in docker" is
"add ``privileged: true``" — without any qualification that this
is appropriate only for short-lived debugging.

What's flagged
--------------
Per file, line-level findings — one per offending key. The detector
walks the YAML structurally so it ignores commented lines and
correctly attributes each finding to its file:line.

What's NOT flagged
------------------
* ``privileged: false`` (or any falsy form)
* ``cap_add`` lists that do not include ``ALL`` / ``SYS_ADMIN`` etc.
  (``cap_add: [SYS_ADMIN]`` IS flagged — it's a known escape).
* Files that are not docker-compose YAML (no top-level
  ``services:`` key).
* Lines or files with a ``# compose-priv-ok`` (line) or
  ``compose-priv-ok-file`` (anywhere) marker.

Refs
----
* CWE-250: Execution with Unnecessary Privileges
* CWE-269: Improper Privilege Management
* docker docs — Compose file reference, ``privileged``, ``cap_add``,
  ``security_opt``, ``pid``, ``ipc``, ``network_mode``,
  ``userns_mode``
* CIS Docker Benchmark §5.4 — Ensure that privileged containers
  are not used

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*compose-priv-ok\b")
SUPPRESS_FILE = re.compile(r"compose-priv-ok-file\b")

# We do a structural-but-lightweight scan: track the indentation of
# the current `services:` block and the current service name, then
# flag specific keys at the per-service level.

SERVICES_RE = re.compile(r"^services\s*:\s*$")
SERVICE_NAME_RE = re.compile(r"^(\s+)([A-Za-z0-9_.-]+)\s*:\s*(?:#.*)?$")
KEY_RE = re.compile(r"^(\s+)([A-Za-z0-9_]+)\s*:\s*(.*?)\s*(?:#.*)?$")
LIST_ITEM_RE = re.compile(r"^(\s+)-\s*(.*?)\s*(?:#.*)?$")

# Strings that, if present in a list value (cap_add or security_opt),
# trigger a finding.
DANGEROUS_CAPS = {
    "ALL",
    "SYS_ADMIN",
    "SYS_PTRACE",
    "SYS_MODULE",
    "DAC_READ_SEARCH",
    "NET_ADMIN",
}
DANGEROUS_SECOPT = re.compile(
    r"""^['"]?(seccomp\s*[:=]\s*unconfined|apparmor\s*[:=]\s*unconfined|no-new-privileges\s*[:=]\s*false)['"]?$""",
    re.IGNORECASE,
)


def _truthy(v: str) -> bool:
    s = v.strip().strip("'\"").lower()
    return s in {"true", "yes", "on", "1"}


def _falsy(v: str) -> bool:
    s = v.strip().strip("'\"").lower()
    return s in {"false", "no", "off", "0"}


def _strip_quotes(v: str) -> str:
    return v.strip().strip("'\"")


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings
    if "services:" not in source and not SERVICES_RE.search(source):
        # Not a compose file.
        return findings

    in_services = False
    services_indent = -1
    service_indent = -1
    in_service = False

    # When we are inside a list-valued key like cap_add / security_opt
    current_list_key = None
    current_list_indent = -1
    current_list_start_line = 0

    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        # Compute leading indent (spaces only; tabs treated as 1).
        stripped = raw.lstrip(" \t")
        indent = len(raw) - len(stripped)

        # Top-level `services:`
        if indent == 0 and SERVICES_RE.match(raw):
            in_services = True
            services_indent = 0
            in_service = False
            current_list_key = None
            continue

        # Other top-level key — leave services block.
        if indent == 0 and in_services:
            in_services = False
            in_service = False
            current_list_key = None

        if not in_services:
            continue

        # Detect a service name: indent strictly greater than services_indent
        # AND a key with no inline value (or a value that is empty).
        m_svc = SERVICE_NAME_RE.match(raw)
        if m_svc and indent > services_indent and (
            service_indent == -1 or indent <= service_indent
        ):
            service_indent = indent
            in_service = True
            current_list_key = None
            continue

        if not in_service:
            continue

        # If we were collecting a list and this line is no longer a
        # list item at the right indent, close the list.
        if current_list_key is not None:
            m_li = LIST_ITEM_RE.match(raw)
            if m_li and indent > current_list_indent:
                item = _strip_quotes(m_li.group(2))
                if current_list_key == "cap_add":
                    if item.upper() in DANGEROUS_CAPS:
                        findings.append(
                            (
                                i,
                                f"`cap_add: [{item}]` grants dangerous Linux capability — likely host escape",
                            )
                        )
                elif current_list_key == "security_opt":
                    if DANGEROUS_SECOPT.match(item):
                        findings.append(
                            (
                                i,
                                f"`security_opt: [{item}]` disables kernel security filters",
                            )
                        )
                continue
            else:
                current_list_key = None  # close list, fall through

        # Per-service key with inline value
        m_kv = KEY_RE.match(raw)
        if not m_kv:
            continue
        key = m_kv.group(2)
        val = m_kv.group(3)

        # Privileged
        if key == "privileged":
            if val and _truthy(val):
                findings.append(
                    (i, "`privileged: true` grants ~all host capabilities — host escape"),
                )
            elif val and _falsy(val):
                pass

        # Namespace shares
        elif key == "pid" and val and _strip_quotes(val).lower() == "host":
            findings.append((i, "`pid: host` shares host PID namespace — escape vector"))
        elif key == "ipc" and val and _strip_quotes(val).lower() == "host":
            findings.append((i, "`ipc: host` shares host IPC namespace — escape vector"))
        elif key == "network_mode" and val and _strip_quotes(val).lower() == "host":
            findings.append(
                (i, "`network_mode: host` shares host network stack — bypasses port isolation")
            )
        elif key == "userns_mode" and val and _strip_quotes(val).lower() == "host":
            findings.append(
                (i, "`userns_mode: host` opts out of user-namespace remapping")
            )

        # List-valued keys (no inline value; entries follow indented).
        elif key in ("cap_add", "security_opt") and not val:
            current_list_key = key
            current_list_indent = indent
            current_list_start_line = i

        # Inline-flow form: cap_add: [ALL]
        elif key == "cap_add" and val.startswith("["):
            inner = val.strip("[]")
            for item in inner.split(","):
                token = _strip_quotes(item).upper()
                if token in DANGEROUS_CAPS:
                    findings.append(
                        (
                            i,
                            f"`cap_add: [{token}]` grants dangerous Linux capability — likely host escape",
                        )
                    )
        elif key == "security_opt" and val.startswith("["):
            inner = val.strip("[]")
            for item in inner.split(","):
                token = _strip_quotes(item)
                if DANGEROUS_SECOPT.match(token):
                    findings.append(
                        (
                            i,
                            f"`security_opt: [{token}]` disables kernel security filters",
                        )
                    )

    return findings


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    seen = set()
    patterns = (
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "*.compose.yml",
        "*.compose.yaml",
    )
    for pattern in patterns:
        for sub in sorted(path.rglob(pattern)):
            if sub.is_file() and sub not in seen:
                seen.add(sub)
                yield sub


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for root in paths:
        for f in _iter_files(root):
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

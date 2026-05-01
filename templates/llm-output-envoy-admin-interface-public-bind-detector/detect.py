#!/usr/bin/env python3
"""
llm-output-envoy-admin-interface-public-bind-detector

Flags Envoy proxy configurations whose `admin` interface is bound to a
publicly routable address (`0.0.0.0`, `::`, `[::]`, or any non-loopback
host). The Envoy admin endpoint exposes `/quitquitquit`, `/clusters`,
`/config_dump` (which leaks TLS material in some setups), `/runtime`,
and `/server_info`. Reachable from the network, it is a one-step path
to draining traffic, dumping live cluster state, or reading the running
configuration.

Maps to:
- CWE-732: Incorrect Permission Assignment for Critical Resource
- CWE-668: Exposure of Resource to Wrong Sphere
- Envoy upstream guidance: bind admin to 127.0.0.1 / Unix socket only.

LLMs reach for `0.0.0.0` because it "just works" inside containers and
because the difference between "loopback only" and "all interfaces" is
a single character.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
files matching `*.yaml`, `*.yml`, `*.json`). Exit codes:
  0 = no findings, 1 = findings (printed to stdout), 2 = usage error.

Heuristic
---------
We do a textual line-window scan rather than parse YAML/JSON, because
Envoy configs are routinely templated (Helm, Jinja, raw envsubst) and
because we want to flag the textual capability even when the value is
later overridden.

Steps:
1. Find a line that names the admin block. Both YAML (`admin:`) and
   JSON (`"admin":`) are accepted.
2. Within the next ~30 non-blank lines, look for a `socket_address` /
   `address` mapping whose `address:` value is a non-loopback host.
3. Loopback values that we accept silently: `127.0.0.1`, `127.0.0.x`,
   `::1`, `localhost`. Unix domain sockets (`pipe:` / `path:`) are also
   accepted.
4. Anything else -- `0.0.0.0`, `::`, `[::]`, `0:0:0:0:0:0:0:0`, an
   actual external IP, or a templated `{{ .Values.host }}` -- is
   flagged. Templated values are flagged as SENSITIVE because we cannot
   prove what `values.yaml` will resolve them to.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Optional

# YAML or JSON key naming the admin block.
_ADMIN_KEY = re.compile(r"""^\s*(?:-\s+)?["']?admin["']?\s*:\s*(?:\{|$|#)""")

# `address: <value>` line. Captures bare hosts, quoted hosts, and Helm
# `{{ .Values.x }}` tokens.
_ADDRESS_LINE = re.compile(
    r"""^\s*["']?address["']?\s*:\s*["']?(?P<val>[^"',}\s#]+)"""
)

# `socket_address:` marker (we want to bias the lookahead toward the
# real bind, not other `address:` keys like access-log addresses).
_SOCKET_ADDR = re.compile(r"""^\s*["']?socket_address["']?\s*:""")

# Unix-socket alternatives that are safe.
_PIPE_KEY = re.compile(r"""^\s*["']?(?:pipe|path)["']?\s*:""")

_BLANK_OR_COMMENT = re.compile(r"^\s*(#.*|//.*)?$")

_LOOPBACK_LITERALS = {
    "127.0.0.1",
    "::1",
    "localhost",
    "0:0:0:0:0:0:0:1",
    "[::1]",
}


def _is_loopback(val: str) -> bool:
    v = val.strip().strip('"').strip("'").lower()
    if v in _LOOPBACK_LITERALS:
        return True
    # 127.0.0.x range
    if re.match(r"^127\.\d+\.\d+\.\d+$", v):
        return True
    return False


def _is_wildcard(val: str) -> bool:
    v = val.strip().strip('"').strip("'").lower()
    return v in {"0.0.0.0", "::", "[::]", "0:0:0:0:0:0:0:0", "*"}


def _is_templated(val: str) -> bool:
    return "{{" in val or "${" in val or "{%" in val


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if not _ADMIN_KEY.match(line):
            i += 1
            continue

        admin_lineno = i + 1
        admin_indent = len(line) - len(line.lstrip())

        # Look ahead up to 30 non-blank lines for an address binding.
        j = i + 1
        scanned = 0
        bind_val: Optional[str] = None
        bind_line = admin_lineno
        saw_socket_addr = False
        saw_pipe = False
        while j < n and scanned < 30:
            child = lines[j]
            if _BLANK_OR_COMMENT.match(child):
                j += 1
                continue
            child_indent = len(child) - len(child.lstrip())
            # Dedent past the admin block -> stop.
            if child_indent <= admin_indent and not child.lstrip().startswith("-"):
                break
            if _SOCKET_ADDR.match(child):
                saw_socket_addr = True
            if _PIPE_KEY.match(child):
                saw_pipe = True
            m = _ADDRESS_LINE.match(child)
            if m and saw_socket_addr:
                bind_val = m.group("val")
                bind_line = j + 1
                break
            j += 1
            scanned += 1

        if saw_pipe and bind_val is None:
            # Unix domain socket -> safe.
            i = max(i + 1, j)
            continue

        if bind_val is None:
            # Admin block declared with no resolvable bind address. Envoy
            # requires one, so this is almost certainly a templated or
            # truncated config; flag as sensitive surface.
            findings.append(
                f"{path}:{admin_lineno}: envoy admin block declared with "
                f"no resolvable bind address (CWE-668): treat as SENSITIVE"
            )
            i = max(i + 1, j)
            continue

        if _is_loopback(bind_val):
            i = max(i + 1, j)
            continue

        if _is_wildcard(bind_val):
            findings.append(
                f"{path}:{bind_line}: envoy admin interface bound to "
                f"wildcard address (CWE-732, exposes /quitquitquit, "
                f"/config_dump, /clusters): address={bind_val}"
            )
        elif _is_templated(bind_val):
            findings.append(
                f"{path}:{bind_line}: envoy admin interface bound to "
                f"templated address (CWE-668, cannot prove loopback): "
                f"SENSITIVE address={bind_val}"
            )
        else:
            findings.append(
                f"{path}:{bind_line}: envoy admin interface bound to "
                f"non-loopback address (CWE-732): address={bind_val}"
            )
        i = max(i + 1, j)
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.endswith((".yaml", ".yml", ".json", ".tpl")):
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

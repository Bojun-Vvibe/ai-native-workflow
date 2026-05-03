#!/usr/bin/env python3
"""
llm-output-pulsar-authentication-disabled-detector

Flags Apache Pulsar broker / proxy configurations that explicitly
disable authentication.

Pulsar's broker (default port 6650 / 8080) and proxy (default 6650
/ 8080) both gate every produce / consume / admin call through
`authenticationEnabled`. With the flag off, anyone who can reach
the broker port can:

- create / delete tenants, namespaces and topics,
- publish to and subscribe from any topic,
- read every retained message (Pulsar persists messages by default
  via BookKeeper),
- reconfigure cluster-level policies through the admin REST API
  (port 8080 / 8443).

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-862: Missing Authorization (because Pulsar's
  authorization layer is gated by authentication; with auth off,
  authorization is not consulted).

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks broker.conf, proxy.conf, standalone.conf, *.conf,
*.properties, *.yaml, *.yml, *.sh, *.bash, docker-compose*.yml,
*.tf).

Heuristic
---------
We flag, outside `#` / `//` comments:

1. `authenticationEnabled` set to a falsy value (`false`, `False`,
   `0`, `no`, `off`) in a Pulsar conf file or YAML / Helm values.
2. `authorizationEnabled` set to a falsy value in the same files
   (functionally equivalent to "no auth at all" — Pulsar will
   short-circuit the check).
3. CLI / env form: `PULSAR_PREFIX_authenticationEnabled=false`
   (Pulsar's standard env-var override prefix).
4. Docker / Helm form: `--authenticationEnabled=false` flag.

Each occurrence emits one finding line. Exit codes:
  0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_FALSY = {"false", "0", "no", "off"}

# Conf / properties / YAML form: `authenticationEnabled=false` or
# `authenticationEnabled: false` or `authenticationEnabled false`.
_KV = re.compile(
    r"""(?P<key>\b(?:authenticationEnabled|authorizationEnabled))"""
    r"""\s*[:=\s]\s*['"]?(?P<val>[A-Za-z0-9_]+)['"]?"""
)

# Env-var override form Pulsar uses in containers:
# PULSAR_PREFIX_authenticationEnabled=false   (shell / Dockerfile env)
# PULSAR_PREFIX_authenticationEnabled: "false"  (compose / Helm YAML)
_ENV = re.compile(
    r"""\bPULSAR_PREFIX_(?P<key>authenticationEnabled|authorizationEnabled)"""
    r"""\s*[:=]\s*['"]?(?P<val>[A-Za-z0-9_]+)['"]?"""
)

# CLI flag form: --authenticationEnabled=false (Helm values, args lists)
_CLI = re.compile(
    r"""--(?P<key>authenticationEnabled|authorizationEnabled)"""
    r"""\s*=\s*['"]?(?P<val>[A-Za-z0-9_]+)['"]?"""
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        elif (
            ch == "/"
            and i + 1 < len(line)
            and line[i + 1] == "/"
            and not in_s
            and not in_d
        ):
            break
        out.append(ch)
        i += 1
    return "".join(out)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        for m in _ENV.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: PULSAR_PREFIX_{m.group('key')} "
                    f"disabled (CWE-306, Pulsar broker accepts "
                    f"unauthenticated clients): {raw.strip()[:160]}"
                )
                continue

        for m in _CLI.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: --{m.group('key')}=false "
                    f"(CWE-306, Pulsar auth disabled on CLI): "
                    f"{raw.strip()[:160]}"
                )
                continue

        # Plain key=value -- but only if the line did NOT already
        # match the env / CLI form above (those have richer context
        # and we don't want to double-report).
        if _ENV.search(line) or _CLI.search(line):
            continue
        for m in _KV.finditer(line):
            if m.group("val").lower() in _FALSY:
                findings.append(
                    f"{path}:{lineno}: {m.group('key')} disabled "
                    f"(CWE-306/CWE-862, Pulsar broker / proxy "
                    f"unauthenticated): {raw.strip()[:160]}"
                )
    return findings


_TARGET_NAMES = (
    "broker.conf",
    "proxy.conf",
    "standalone.conf",
    "functions_worker.yml",
)
_TARGET_EXTS = (
    ".conf", ".properties", ".yaml", ".yml",
    ".sh", ".bash", ".tpl", ".tf", ".env",
)


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

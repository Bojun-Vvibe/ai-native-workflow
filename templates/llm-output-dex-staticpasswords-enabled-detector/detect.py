#!/usr/bin/env python3
r"""
llm-output-dex-staticpasswords-enabled-detector

Flags Dex (https://github.com/dexidp/dex) configurations that enable
the **static passwords** identity backend in production-shaped
deployments. Either:

  enablePasswordDB: true

is set together with a `staticPasswords:` block, or `staticPasswords`
contains the well-known demo / example credentials (`admin@example.com`
with bcrypt hashes commonly copy-pasted from the Dex tutorial).

Maps to:
- CWE-798: Use of Hard-coded Credentials.
- CWE-1392: Use of Default Credentials.
- CWE-287: Improper Authentication.

Background
----------
Dex is an OIDC identity broker. The recommended production path is
to federate to a real upstream IdP (LDAP, GitHub, OIDC, SAML, etc.)
and leave `enablePasswordDB: false`. The `staticPasswords:` block
is intended for `getting started` / dev only. The Dex docs
(https://dexidp.io/docs/connectors/local/) ship a hash for
`password` (`$2a$10$33EMT0cVYVlPy6WAMCLsceLYjWhuHpbz5yuZxu/GAFj03J9Lytjuy`)
and an email of `admin@example.com`. LLMs frequently copy this
verbatim into Helm values / k8s ConfigMaps and also flip
`enablePasswordDB` on, producing a public OIDC issuer with a
known-good credential.

Heuristic
---------
A file is "dex-related" if it mentions:
  - `dexidp/dex` image / chart
  - `quay.io/dexidp/dex` image
  - the tokens `enablePasswordDB`, `staticPasswords:`,
    `staticClients:` together with `issuer:` / `connectors:`

Inside such a file, outside `#` / `//` comments, we flag:

1. `enablePasswordDB: true` (any case, any indentation).
2. A `staticPasswords:` block that contains an entry with email
   `admin@example.com`, OR with a bcrypt hash starting with
   `$2a$10$33EMT0cVYVlPy6WAMCLsce` (the canonical Dex tutorial
   hash for `password`).
3. `staticPasswords:` block + `enablePasswordDB: true` in the
   same file (treated as one finding per occurrence).

Each occurrence emits one finding line.

Stdlib-only.

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List


_DEX_HINT = re.compile(
    r"""\b(?:dexidp/dex|quay\.io/dexidp/dex|enablePasswordDB|staticPasswords|staticClients)\b""",
    re.IGNORECASE,
)
_DEX_CONTEXT = re.compile(
    r"""(?m)^\s*(?:issuer|connectors|staticClients|staticPasswords|storage)\s*:""",
    re.IGNORECASE,
)

_ENABLE_TRUE = re.compile(
    r"""^(?P<i>\s*)enablePasswordDB\s*:\s*true\b""",
    re.IGNORECASE,
)
_DEMO_EMAIL = re.compile(
    r"""\bemail\s*:\s*["']?admin@example\.com["']?\b""",
    re.IGNORECASE,
)
_DEMO_HASH = re.compile(
    r"""\$2a\$10\$33EMT0cVYVlPy6WAMCLsce[A-Za-z0-9./]*"""
)
_STATIC_BLOCK = re.compile(
    r"""^(?P<i>\s*)staticPasswords\s*:\s*$""",
    re.IGNORECASE,
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
        out.append(ch)
        i += 1
    return "".join(out)


def _is_dex_file(text: str) -> bool:
    if not _DEX_HINT.search(text):
        return False
    # Reduce false positives in unrelated docs that just mention "dex":
    # require at least one config-shaped key.
    if _DEX_CONTEXT.search(text):
        return True
    # Or an explicit image reference.
    if re.search(r"""\b(?:quay\.io/)?dexidp/dex(?::|@)""", text):
        return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if not _is_dex_file(text):
        return findings

    has_static_block = False
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        if _STATIC_BLOCK.match(_strip_comment(raw)):
            has_static_block = True
            break

    has_enable_true = False
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        if _ENABLE_TRUE.match(_strip_comment(raw)):
            has_enable_true = True
            break

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        if _ENABLE_TRUE.match(line):
            findings.append(
                f"{path}:{lineno}: dex enablePasswordDB: true keeps the "
                f"local static-password backend on; production should "
                f"federate to a real IdP (CWE-287/CWE-798): "
                f"{raw.strip()[:160]}"
            )
            continue

        if _DEMO_EMAIL.search(line) and has_static_block:
            findings.append(
                f"{path}:{lineno}: dex staticPasswords entry uses demo "
                f"email admin@example.com from the Dex tutorial "
                f"(CWE-1392/CWE-798): {raw.strip()[:160]}"
            )
            continue

        if _DEMO_HASH.search(line) and has_static_block:
            findings.append(
                f"{path}:{lineno}: dex staticPasswords entry uses the "
                f"canonical tutorial bcrypt hash for 'password' "
                f"(CWE-798/CWE-1392): {raw.strip()[:160]}"
            )
            continue

    # Combined finding: staticPasswords block + enablePasswordDB true
    # in same file but neither demo email nor demo hash present
    # (still risky -- emit if not already covered).
    if has_static_block and has_enable_true and not findings:
        findings.append(
            f"{path}:0: dex enables staticPasswords AND "
            f"enablePasswordDB: true together; recommended pattern is "
            f"to disable the password DB in production "
            f"(CWE-287/CWE-798)"
        )

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "values.yaml",
    "config.yaml",
    "dex.yaml",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".tf",
    ".tpl", ".env", ".cfg", ".conf",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
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

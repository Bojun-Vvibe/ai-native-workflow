#!/usr/bin/env python3
"""
llm-output-superset-secret-key-default-detector

Flags Apache Superset configurations that leave SECRET_KEY at the
upstream default value or another well-known placeholder.

Superset uses Flask's `SECRET_KEY` to sign session cookies, the
CSRF token, and (via Fernet) the encrypted database-connection
URIs stored in the metadata DB (`encrypted_extra`). With a known
SECRET_KEY, an attacker can:

- forge a session cookie for the `Admin` role and bypass login,
- mint a valid CSRF token for any form,
- decrypt every saved database-connection URI in the metadata DB
  (often containing prod warehouse credentials).

The upstream `superset_config.py.example` shipped a placeholder
of `\\2dEDC3MOdPRJHsJ` for many releases (still the value used in
copy-paste blog posts), and the official docker-compose ships
`SUPERSET_SECRET_KEY=TEST_NON_DEV_SECRET` in `docker/.env-non-dev`
with a giant "CHANGE THIS" warning above it. LLMs reach for both
because they appear verbatim in the upstream repo.

Maps to:
- CWE-798: Use of Hard-coded Credentials.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-330: Use of Insufficiently Random Values (downstream).

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks superset_config.py, *.py, *.env, .env, *.yaml, *.yml,
*.sh, *.bash, Dockerfile, docker-compose*.yml).

Heuristic
---------
We flag, outside `#` / `//` comments:

1. Python assignment `SECRET_KEY = "<known-weak>"` or
   `SECRET_KEY: str = "<known-weak>"` in any *.py file.
2. Env-var form `SUPERSET_SECRET_KEY=<known-weak>` (or
   `SUPERSET_SECRET_KEY: <known-weak>`) in `.env`, Compose,
   Dockerfile, Helm values.
3. CLI / Helm `--set` form: `--set superset.secretKey=<known-weak>`.

Known-weak set:
    \\2dEDC3MOdPRJHsJ          (upstream config example)
    TEST_NON_DEV_SECRET        (upstream docker .env-non-dev)
    your_secret_key_here       (LLM placeholder favourite)
    changeme                   (LLM placeholder favourite)
    secret                     (LLM placeholder favourite)
    superset                   (LLM placeholder favourite)
    please_change_me_in_production  (common copy-paste filler)
    thisisnotasecret           (Flask tutorial filler)

Each occurrence emits one finding line. Exit codes:
  0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_WEAK = {
    r"\2dedc3modprjhsj",
    "test_non_dev_secret",
    "your_secret_key_here",
    "changeme",
    "change_me",
    "change-me",
    "secret",
    "superset",
    "please_change_me_in_production",
    "thisisnotasecret",
    "default_secret",
    "supersecret",
    "mysecretkey",
}

# Python assignment: SECRET_KEY = "..." (also handles SECRET_KEY: str = "...")
_PY_ASSIGN = re.compile(
    r"""\bSECRET_KEY\b\s*(?::\s*[A-Za-z_][A-Za-z0-9_\[\], ]*\s*)?="""
    r"""\s*(?P<q>['"])(?P<val>.*?)(?P=q)"""
)

# Env-var form for the official docker image and Helm chart.
# SUPERSET_SECRET_KEY=val   |   SUPERSET_SECRET_KEY: "val"
_ENV_ASSIGN = re.compile(
    r"""\bSUPERSET_SECRET_KEY\s*[:=]\s*['"]?(?P<val>[^\s'"#]+)['"]?"""
)

# Helm CLI form: --set superset.secretKey=val
_HELM_SET = re.compile(
    r"""--set\s+(?:[A-Za-z0-9_.-]+\.)?secretKey\s*=\s*['"]?(?P<val>[^\s'"]+)['"]?""",
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
        elif (
            ch == "/"
            and i + 1 < len(line)
            and line[i + 1] == "/"
            and not in_s
            and not in_d
            and not (i > 0 and line[i - 1] == ":")
        ):
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _is_weak(val: str) -> bool:
    low = val.lower()
    if low in _WEAK:
        return True
    # The upstream example value contains an embedded backslash;
    # accept both the literal and the unescaped Python view.
    if low.replace("\\\\", "\\") in _WEAK:
        return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        for m in _PY_ASSIGN.finditer(line):
            if _is_weak(m.group("val")):
                findings.append(
                    f"{path}:{lineno}: SECRET_KEY = '{m.group('val')[:40]}' "
                    f"matches a known-weak Superset placeholder "
                    f"(CWE-798/CWE-1188): {raw.strip()[:160]}"
                )
                continue

        for m in _ENV_ASSIGN.finditer(line):
            if _is_weak(m.group("val")):
                findings.append(
                    f"{path}:{lineno}: SUPERSET_SECRET_KEY="
                    f"'{m.group('val')[:40]}' matches a known-weak "
                    f"Superset placeholder (CWE-798/CWE-1188): "
                    f"{raw.strip()[:160]}"
                )
                continue

        for m in _HELM_SET.finditer(line):
            if _is_weak(m.group("val")):
                findings.append(
                    f"{path}:{lineno}: --set ...secretKey="
                    f"'{m.group('val')[:40]}' matches a known-weak "
                    f"Superset placeholder (CWE-798/CWE-1188): "
                    f"{raw.strip()[:160]}"
                )
    return findings


_TARGET_NAMES = (
    "superset_config.py",
    "dockerfile",
    ".env",
    ".env-non-dev",
    ".env-local",
)
_TARGET_EXTS = (
    ".py", ".yaml", ".yml", ".sh", ".bash", ".env",
    ".tpl", ".tf", ".conf",
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

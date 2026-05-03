#!/usr/bin/env python3
"""
llm-output-couchbase-default-administrator-credentials-detector

Flags Couchbase Server cluster-init / setup configurations that
ship with the well-known default Administrator username together
with a weak / default cluster password.

Couchbase's `couchbase-cli cluster-init` and the equivalent REST
endpoint (`POST /pools/default`) take a username and password that
become the full-access cluster Administrator. Once leaked, that
account can:

- read and write every bucket (i.e. all customer data),
- spin up XDCR replications to an attacker-controlled remote
  cluster (silent exfil),
- run N1QL `EXECUTE FUNCTION` to load arbitrary JavaScript into the
  query service,
- enable the CLI / REST audit-log purge (cover tracks).

Maps to:
- CWE-798: Use of Hard-coded Credentials.
- CWE-521: Weak Password Requirements.

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks docker-compose*.yml, *.yaml, *.yml, *.sh, *.bash, *.tf,
*.env, Dockerfile, *.conf).

Heuristic
---------
We flag, outside `#` / `//` comments, any line that pairs the
default `Administrator` username with one of the well-known weak
cluster passwords on the same line, or the `couchbase-cli
cluster-init` invocation with such a password, in any of these
forms:

1. `couchbase-cli cluster-init ... --cluster-username Administrator
   --cluster-password password`  (CLI form, default user + weak pw)
2. `--username Administrator --password password` against the
   Couchbase REST endpoint via `curl ... /pools/default`.
3. `COUCHBASE_ADMINISTRATOR_USERNAME=Administrator` together with
   `COUCHBASE_ADMINISTRATOR_PASSWORD=password` in env / Compose.
4. YAML keys `cluster.username: Administrator` plus
   `cluster.password: password` (Helm values style) on lines within
   a small window.

The known-weak password set is the documented Couchbase quickstart
defaults plus the most common LLM-suggested fillers:

    password, Password1, couchbase, admin, administrator, 123456,
    changeme, default, secret

Each occurrence emits one finding line. Exit codes:
  0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_WEAK = {
    "password",
    "password1",
    "couchbase",
    "admin",
    "administrator",
    "123456",
    "changeme",
    "default",
    "secret",
}

# couchbase-cli cluster-init ... with --cluster-username and
# --cluster-password (or short -u / -p) on the same line.
_CLI_INIT = re.compile(
    r"""couchbase-cli\s+cluster-init\b[^\n]*?"""
    r"""(?:--cluster-username|--username|-u)\s+['"]?(?P<user>[A-Za-z0-9_.-]+)['"]?"""
    r"""[^\n]*?"""
    r"""(?:--cluster-password|--password|-p)\s+['"]?(?P<pw>[^\s'"]+)['"]?""",
    re.IGNORECASE,
)

# curl-style call to /pools/default carrying -u Administrator:password
_CURL_AUTH = re.compile(
    r"""curl\b[^\n]*?-u\s+['"]?(?P<user>[A-Za-z0-9_.-]+):(?P<pw>[^\s'"]+)['"]?[^\n]*?/pools/default""",
    re.IGNORECASE,
)

# Env-var form (Compose / Dockerfile / shell):
# COUCHBASE_ADMINISTRATOR_USERNAME=Administrator
# COUCHBASE_ADMINISTRATOR_PASSWORD=password
_ENV_USER = re.compile(
    r"""\bCOUCHBASE_ADMINISTRATOR_USERNAME\s*[:=]\s*['"]?(?P<user>[A-Za-z0-9_.-]+)['"]?""",
    re.IGNORECASE,
)
_ENV_PW = re.compile(
    r"""\bCOUCHBASE_ADMINISTRATOR_PASSWORD\s*[:=]\s*['"]?(?P<pw>[^\s'"]+)['"]?""",
    re.IGNORECASE,
)

# Helm / YAML form: cluster.username / cluster.password
_YAML_USER = re.compile(
    r"""^\s*(?:cluster[._]?)?username\s*:\s*['"]?(?P<user>[A-Za-z0-9_.-]+)['"]?\s*$""",
    re.IGNORECASE,
)
_YAML_PW = re.compile(
    r"""^\s*(?:cluster[._]?)?password\s*:\s*['"]?(?P<pw>[^\s'"]+)['"]?\s*$""",
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


def _is_default_admin(user: str, pw: str) -> bool:
    return user.lower() == "administrator" and pw.lower() in _WEAK


def _join_line_continuations(text: str) -> List[Tuple[int, str]]:
    """Return list of (start_lineno, joined_logical_line).

    Handles shell backslash-newline so multi-line CLI invocations
    appear as a single logical line for regex matching.
    """
    raw_lines = text.splitlines()
    out: List[Tuple[int, str]] = []
    i = 0
    while i < len(raw_lines):
        start = i + 1
        buf = raw_lines[i]
        while buf.rstrip().endswith("\\") and i + 1 < len(raw_lines):
            buf = buf.rstrip()[:-1] + " " + raw_lines[i + 1]
            i += 1
        out.append((start, buf))
        i += 1
    return out


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    logical = _join_line_continuations(text)

    # Pass 1: single-line CLI / curl / env-pair-on-same-line forms.
    for lineno, raw in logical:
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        for m in _CLI_INIT.finditer(line):
            if _is_default_admin(m.group("user"), m.group("pw")):
                findings.append(
                    f"{path}:{lineno}: couchbase-cli cluster-init with "
                    f"default Administrator + weak password "
                    f"'{m.group('pw')}' (CWE-798/CWE-521): "
                    f"{raw.strip()[:160]}"
                )

        for m in _CURL_AUTH.finditer(line):
            if _is_default_admin(m.group("user"), m.group("pw")):
                findings.append(
                    f"{path}:{lineno}: curl /pools/default with default "
                    f"Administrator + weak password '{m.group('pw')}' "
                    f"(CWE-798): {raw.strip()[:160]}"
                )

    # Pass 2: cross-line env-var pair (Compose env: blocks, .env
    # files). Look for USER=Administrator on one line, PW=<weak>
    # within +/- 5 lines.
    env_users: List[Tuple[int, str, str]] = []
    env_pws: List[Tuple[int, str, str]] = []
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)
        mu = _ENV_USER.search(line)
        if mu:
            env_users.append((lineno, mu.group("user"), raw))
        mp = _ENV_PW.search(line)
        if mp:
            env_pws.append((lineno, mp.group("pw"), raw))

    for ulineno, user, uraw in env_users:
        if user.lower() != "administrator":
            continue
        for plineno, pw, praw in env_pws:
            if abs(plineno - ulineno) > 8:
                continue
            if pw.lower() in _WEAK:
                findings.append(
                    f"{path}:{plineno}: COUCHBASE_ADMINISTRATOR_PASSWORD "
                    f"= '{pw}' paired with default Administrator user "
                    f"at line {ulineno} (CWE-798): {praw.strip()[:160]}"
                )

    # Pass 3: YAML cluster.username / cluster.password pair within
    # an 8-line window (Helm values, Couchbase Operator CR).
    yaml_users: List[Tuple[int, str, str]] = []
    yaml_pws: List[Tuple[int, str, str]] = []
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)
        mu = _YAML_USER.match(line)
        if mu:
            yaml_users.append((lineno, mu.group("user"), raw))
        mp = _YAML_PW.match(line)
        if mp:
            yaml_pws.append((lineno, mp.group("pw"), raw))

    for ulineno, user, uraw in yaml_users:
        if user.lower() != "administrator":
            continue
        for plineno, pw, praw in yaml_pws:
            if abs(plineno - ulineno) > 8:
                continue
            if pw.lower() in _WEAK:
                findings.append(
                    f"{path}:{plineno}: YAML password '{pw}' paired "
                    f"with default Administrator user at line "
                    f"{ulineno} (CWE-798/CWE-521): {praw.strip()[:160]}"
                )

    return findings


_TARGET_NAMES = (
    "dockerfile",
    ".env",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".tf", ".env",
    ".conf", ".tpl",
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

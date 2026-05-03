#!/usr/bin/env python3
r"""
llm-output-oauth2-proxy-skip-auth-regex-permissive-detector

Flags `oauth2-proxy` deployments configured with a permissive
`--skip-auth-regex` / `skip_auth_regex` / `--skip-auth-route` /
`skip_auth_routes` value that effectively disables authentication
for the upstream.

Maps to:
- CWE-284: Improper Access Control.
- CWE-287: Improper Authentication.
- CWE-697: Incorrect Comparison (overly broad regex).

Background
----------
`oauth2-proxy` (https://github.com/oauth2-proxy/oauth2-proxy) sits in
front of an upstream and forces an OIDC / OAuth2 round-trip. The
`--skip-auth-regex` flag (deprecated alias for `--skip-auth-route`)
takes a Go regexp that, if matched, lets a request through with NO
authentication. LLMs frequently emit:

    --skip-auth-regex='^.*$'
    --skip-auth-regex='.*'
    --skip-auth-regex='^/.*'
    skip_auth_regex = [ "^/" ]
    skip_auth_routes = [ "GET=^.*$" ]

…which fully bypasses the proxy. The upstream then receives
unauthenticated traffic from the public internet.

Heuristic
---------
A file is "oauth2-proxy related" if it mentions:
  - image `quay.io/oauth2-proxy/oauth2-proxy` or
    `bitnami/oauth2-proxy`
  - the binary name `oauth2-proxy`
  - any of the config keys: `skip_auth_regex`, `skip_auth_routes`,
    `skip-auth-regex`, `skip-auth-route`

Inside such a file, outside `#` / `//` comments, we flag any value
whose regex (after stripping a leading HTTP method `=` like
`GET=`) reduces to one of:
  - `.*`
  - `^.*$`
  - `^/.*$` / `^/.*` / `/.*`
  - `^/`
  - `^`     (matches everything)
  - `(?i).*`

We also flag any literal `\b` shaped like the above wrapped in
extra anchors (we strip a single leading `^` and trailing `$`).

Each occurrence emits one finding line.

Stdlib-only.

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List


_O2P_HINT = re.compile(
    r"""\b(?:oauth2[_-]proxy|skip[_-]auth[_-](?:regex|route|routes))\b""",
    re.IGNORECASE,
)
_O2P_IMAGE = re.compile(
    r"""\b(?:quay\.io/oauth2-proxy/oauth2-proxy|bitnami/oauth2-proxy)\b""",
    re.IGNORECASE,
)

# Capture the value after --skip-auth-regex= / --skip-auth-route=
# or yaml/cfg `skip_auth_regex = "..."` / list entries.
_FLAG_VALUE = re.compile(
    r"""--skip[-_]auth[-_](?:regex|route|routes)\s*[= ]\s*(?P<q>['"]?)(?P<v>[^'"\s]+)(?P=q)""",
    re.IGNORECASE,
)
_CFG_SCALAR = re.compile(
    r"""^\s*skip[_-]auth[_-](?:regex|route|routes)\s*[:=]\s*(?P<q>['"])(?P<v>.+?)(?P=q)\s*$""",
    re.IGNORECASE,
)
# yaml list item under skip_auth_regex / skip_auth_routes
_LIST_ITEM = re.compile(
    r"""^\s*(?:-\s*)?(?P<q>['"])(?P<v>.+?)(?P=q)\s*,?\s*$"""
)
_LIST_HEADER = re.compile(
    r"""^\s*skip[_-]auth[_-](?:regex|route|routes)\s*[:=]\s*\[?\s*$""",
    re.IGNORECASE,
)
_INLINE_LIST = re.compile(
    r"""^\s*skip[_-]auth[_-](?:regex|route|routes)\s*[:=]\s*\[(?P<body>.+)\]\s*$""",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


_PERMISSIVE = {
    ".*",
    "^.*",
    "^.*$",
    ".*$",
    "^",
    "^/",
    "^/.*",
    "^/.*$",
    "/.*",
    "/",
    "(?i).*",
    "(?i)^.*$",
    "(.*)",
    "^(.*)$",
}


def _strip_method_prefix(v: str) -> str:
    # Routes can be prefixed like "GET=regex"; we only check the regex.
    m = re.match(r"""^[A-Z]+=(.+)$""", v)
    if m:
        return m.group(1)
    return v


def _is_permissive(value: str) -> bool:
    v = value.strip()
    v = _strip_method_prefix(v)
    if v in _PERMISSIVE:
        return True
    # Strip a wrapping ^...$ once and re-test.
    if v.startswith("^") and v.endswith("$"):
        inner = v[1:-1]
        if inner in {".*", "(.*)", "/.*", "/", ".+"}:
            return True
    # Single dot-star with optional flags.
    if re.fullmatch(r"""\(\?[a-zA-Z]+\)\.\*""", v):
        return True
    return False


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


def _is_o2p_file(text: str) -> bool:
    if _O2P_HINT.search(text):
        return True
    if _O2P_IMAGE.search(text):
        return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if not _is_o2p_file(text):
        return findings

    in_list_block = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        # Inline list form: skip_auth_regex: ["a","b"]
        m_inline = _INLINE_LIST.match(line)
        if m_inline:
            body = m_inline.group("body")
            for vm in re.finditer(
                r"""(?P<q>['"])(?P<v>.+?)(?P=q)""", body
            ):
                v = vm.group("v")
                if _is_permissive(v):
                    findings.append(
                        f"{path}:{lineno}: oauth2-proxy skip_auth* value "
                        f"'{v}' is permissive and bypasses authentication "
                        f"(CWE-284/CWE-287): {raw.strip()[:160]}"
                    )
            in_list_block = False
            continue

        # Multi-line list header.
        if _LIST_HEADER.match(line):
            in_list_block = True
            continue

        if in_list_block:
            mli = _LIST_ITEM.match(line)
            if mli:
                v = mli.group("v")
                if _is_permissive(v):
                    findings.append(
                        f"{path}:{lineno}: oauth2-proxy skip_auth* list "
                        f"entry '{v}' is permissive and bypasses "
                        f"authentication (CWE-284/CWE-287): "
                        f"{raw.strip()[:160]}"
                    )
                continue
            # End of list block.
            if line.strip() in ("]", "") or not line.startswith((" ", "\t", "-", "]")):
                in_list_block = False

        # Scalar: skip_auth_regex = "..."
        ms = _CFG_SCALAR.match(line)
        if ms:
            v = ms.group("v")
            if _is_permissive(v):
                findings.append(
                    f"{path}:{lineno}: oauth2-proxy skip_auth* value "
                    f"'{v}' is permissive and bypasses authentication "
                    f"(CWE-284/CWE-287): {raw.strip()[:160]}"
                )
            continue

        # CLI flag form anywhere on the line.
        for mf in _FLAG_VALUE.finditer(line):
            v = mf.group("v")
            if _is_permissive(v):
                findings.append(
                    f"{path}:{lineno}: oauth2-proxy --skip-auth-* value "
                    f"'{v}' is permissive and bypasses authentication "
                    f"(CWE-284/CWE-287): {raw.strip()[:160]}"
                )

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "oauth2_proxy.cfg",
    "oauth2-proxy.cfg",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".tf",
    ".tpl", ".env", ".cfg", ".conf", ".toml",
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

#!/usr/bin/env python3
"""
llm-output-frps-dashboard-default-credentials-detector

Flags `frps` (fast reverse proxy server) configs that expose the
admin **dashboard** with the upstream default credentials
(`admin` / `admin`), or with no credentials at all.

`frps` ships an HTTP dashboard at `dashboard_addr:dashboard_port`
(default `0.0.0.0:7500`) that lets anyone with network access:

  * see every configured proxy and its remote port mapping,
  * see every connected client (IP, version, run id),
  * close / kick clients,
  * reload the server config (frp >= 0.45 with `enable_remote_config`).

The dashboard is gated by HTTP basic-auth, configured via:

  * `dashboard_user = "..."` and `dashboard_pwd = "..."`  (TOML / INI)
  * `webServer.user = "..."` and `webServer.password = "..."`  (frp >= 0.52 TOML)

The frp README sample shows `dashboard_user = "admin"` and
`dashboard_pwd = "admin"`. LLMs copy that sample verbatim.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-521: Weak Password Requirements
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-306: Missing Authentication for Critical Function
    (when both fields are absent on a `dashboard_addr` config)
  - OWASP A07:2021 Identification and Authentication Failures

Heuristic
---------
We flag any frps-shaped config (TOML / INI / YAML) that:

1. Sets `dashboard_pwd` (or `webServer.password`) to one of the
   well-known default / empty values:

     "admin", "password", "admin123", "frp", "changeme", "" (empty)

2. OR enables the dashboard (any `dashboard_addr` / `dashboard_port`
   / `webServer.port` directive) AND does NOT set a `dashboard_pwd`
   / `webServer.password` anywhere in the same file.

We do NOT flag:

  * frps configs that set `dashboard_pwd` to a non-default value,
  * configs without any `dashboard_*` / `webServer.*` directive
    (dashboard not enabled),
  * docs / README files that show the bad value only inside `#`
    comments.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_DEFAULT_PWDS = {
    "admin",
    "password",
    "admin123",
    "frp",
    "changeme",
    "",
}

# INI / TOML flat:  dashboard_pwd = "admin"
_INI_PWD = re.compile(
    r"""^\s*dashboard_pwd\s*=\s*(?P<v>"[^"]*"|'[^']*'|[^#;\s]+)\s*(?:[#;].*)?$""",
    re.IGNORECASE,
)
_INI_USER = re.compile(
    r"""^\s*dashboard_user\s*=\s*(?P<v>"[^"]*"|'[^']*'|[^#;\s]+)\s*(?:[#;].*)?$""",
    re.IGNORECASE,
)
_INI_DASH_ADDR = re.compile(
    r"""^\s*dashboard_(addr|port)\s*=\s*\S+""",
    re.IGNORECASE,
)

# TOML nested-table form (frp >= 0.52):
#   [webServer]
#     password = "admin"
_TOML_WEBSERVER_HDR = re.compile(
    r"""^\s*\[\s*webServer\s*\]\s*$""", re.IGNORECASE,
)
_TOML_ANY_HDR = re.compile(r"""^\s*\[\s*[A-Za-z0-9_.\-]+\s*\]\s*$""")
_TOML_WS_KEY = re.compile(
    r"""^\s*(?P<k>password|user|port|addr)\s*=\s*(?P<v>"[^"]*"|'[^']*'|[^#;\s]+)""",
    re.IGNORECASE,
)

# YAML form:
#   webServer:
#     password: "admin"
_YAML_WEBSERVER_KEY = re.compile(r"""^(\s*)webServer\s*:\s*(?:#.*)?$""")
_YAML_DEDENT_KEY = re.compile(r"""^(\s*)[A-Za-z0-9_.-]+\s*:""")
_YAML_LEAF = re.compile(
    r"""^(?P<ind>\s*)(?P<k>password|user|port|addr)\s*:\s*["']?(?P<v>[^"'#\n]*?)["']?\s*(?:#.*)?$""",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _looks_like_frp(text: str, path: str) -> bool:
    low = text.lower()
    base = os.path.basename(path).lower()
    if "frp" in base:
        return True
    needles = (
        "[common]",
        "bind_port",
        "bind_addr",
        "dashboard_port",
        "dashboard_pwd",
        "dashboard_user",
        "vhost_http_port",
        "subdomain_host",
        "[webserver]",
        "webserver:",
    )
    return any(n in low for n in needles)


def scan_ini_toml_flat(text: str, path: str) -> List[str]:
    """Handles the legacy [common]-style frps.ini / frps.toml."""
    findings: List[str] = []
    has_dash = False
    pwd_line: Tuple[int, str, str] | None = None  # (lineno, raw, value)
    saw_pwd_key = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if _INI_DASH_ADDR.match(raw):
            has_dash = True
        m = _INI_PWD.match(raw)
        if m:
            saw_pwd_key = True
            pwd_line = (lineno, raw, _unquote(m.group("v")))
    if pwd_line is not None and pwd_line[2].lower() in _DEFAULT_PWDS:
        findings.append(
            f"{path}:{pwd_line[0]}: frps dashboard_pwd is a known "
            f"default value '{pwd_line[2]}' -> dashboard is one curl "
            f"away from full proxy/client takeover (CWE-798/CWE-1188)"
        )
    elif has_dash and not saw_pwd_key:
        # First dashboard_addr/port line.
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if _INI_DASH_ADDR.match(raw):
                findings.append(
                    f"{path}:{lineno}: frps dashboard_addr/port set "
                    f"but no dashboard_pwd configured -> dashboard "
                    f"reachable with no auth (CWE-306/CWE-1188): "
                    f"{raw.strip()[:160]}"
                )
                break
    return findings


def scan_toml_webserver(text: str, path: str) -> List[str]:
    """Handles the frp >= 0.52 [webServer] block in TOML."""
    findings: List[str] = []
    lines = text.splitlines()
    in_ws = False
    has_port_or_addr = False
    pwd_seen: Tuple[int, str, str] | None = None
    for lineno, raw in enumerate(lines, start=1):
        if _TOML_WEBSERVER_HDR.match(raw):
            in_ws = True
            continue
        if in_ws and _TOML_ANY_HDR.match(raw):
            in_ws = False
            continue
        if not in_ws:
            continue
        if _COMMENT_LINE.match(raw):
            continue
        m = _TOML_WS_KEY.match(raw)
        if not m:
            continue
        key = m.group("k").lower()
        val = _unquote(m.group("v"))
        if key in ("port", "addr"):
            has_port_or_addr = True
        if key == "password":
            pwd_seen = (lineno, raw, val)
    if pwd_seen is not None and pwd_seen[2].lower() in _DEFAULT_PWDS:
        findings.append(
            f"{path}:{pwd_seen[0]}: frps [webServer] password is a "
            f"known default value '{pwd_seen[2]}' -> dashboard is "
            f"one curl away from full proxy/client takeover "
            f"(CWE-798/CWE-1188)"
        )
    elif has_port_or_addr and pwd_seen is None:
        # Find header line for the report.
        for lineno, raw in enumerate(lines, start=1):
            if _TOML_WEBSERVER_HDR.match(raw):
                findings.append(
                    f"{path}:{lineno}: frps [webServer] block "
                    f"defined with port/addr but no password -> "
                    f"dashboard reachable with no auth "
                    f"(CWE-306/CWE-1188)"
                )
                break
    return findings


def scan_yaml_webserver(text: str, path: str) -> List[str]:
    """Handles `webServer:` block in YAML (helm values)."""
    findings: List[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _YAML_WEBSERVER_KEY.match(lines[i])
        if not m:
            i += 1
            continue
        base_indent = len(m.group(1))
        ws_line = i + 1
        j = i + 1
        has_port_or_addr = False
        pwd: Tuple[int, str, str] | None = None
        while j < len(lines):
            line = lines[j]
            if line.strip() == "" or _COMMENT_LINE.match(line):
                j += 1
                continue
            md = _YAML_DEDENT_KEY.match(line)
            if md and len(md.group(1)) <= base_indent:
                break
            ml = _YAML_LEAF.match(line)
            if ml and len(ml.group("ind")) > base_indent:
                k = ml.group("k").lower()
                v = ml.group("v").strip()
                if k in ("port", "addr"):
                    has_port_or_addr = True
                if k == "password":
                    pwd = (j + 1, line, v)
            j += 1
        if pwd is not None and pwd[2].lower() in _DEFAULT_PWDS:
            findings.append(
                f"{path}:{pwd[0]}: frps webServer.password is a "
                f"known default value '{pwd[2]}' -> dashboard is "
                f"one curl away from full proxy/client takeover "
                f"(CWE-798/CWE-1188)"
            )
        elif has_port_or_addr and pwd is None:
            findings.append(
                f"{path}:{ws_line}: frps webServer: block defined "
                f"with port/addr but no password -> dashboard "
                f"reachable with no auth (CWE-306/CWE-1188)"
            )
        i = j if j > i else i + 1
    return findings


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    if not _looks_like_frp(text, path):
        return []
    out: List[str] = []
    low = path.lower()
    if low.endswith((".ini", ".conf", ".cfg", ".toml")):
        out.extend(scan_ini_toml_flat(text, path))
    if low.endswith(".toml"):
        out.extend(scan_toml_webserver(text, path))
    if low.endswith((".yaml", ".yml")):
        out.extend(scan_yaml_webserver(text, path))
    return out


_TARGET_EXTS = (".ini", ".toml", ".conf", ".cfg", ".yaml", ".yml")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.lower().endswith(_TARGET_EXTS):
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

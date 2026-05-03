#!/usr/bin/env python3
r"""
llm-output-kong-rbac-disabled-detector

Flags Kong Gateway / Kong Enterprise deployments whose Admin API is
configured with **RBAC disabled** (`enforce_rbac = off` / `KONG_ENFORCE_RBAC=off`),
or whose `kong.conf` / env / Helm values omit RBAC enforcement on a
publicly bound Admin API.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-732: Incorrect Permission Assignment for Critical Resource.

Background
----------
Kong's Admin API (default `:8001` HTTP, `:8444` HTTPS) is the
control plane: anyone who reaches it can add routes, attach plugins,
re-route traffic, and read/modify credentials. Kong Enterprise (and
the OSS edition's `enforce_rbac` knob, present since 2.x) ships with
RBAC **off** by default (`enforce_rbac = off`). Upstream:
- https://github.com/Kong/kong (kong.conf.default, v3.x line)
- https://docs.konghq.com/gateway/latest/kong-enterprise/rbac/

LLMs routinely emit:

    docker run -e "KONG_ADMIN_LISTEN=0.0.0.0:8001" kong:3.7
    enforce_rbac = off
    KONG_ENFORCE_RBAC: "off"

...with the Admin API also bound to a routable address. The result
is an unauthenticated, fully privileged control plane.

Heuristic
---------
A file is "kong-related" if it mentions:
  - `kong:` image tag (`kong:3.x`, `kong/kong-gateway:3.x`)
  - `KONG_ADMIN_LISTEN`, `KONG_ENFORCE_RBAC`, `KONG_ADMIN_GUI_AUTH`
  - `kong.conf` style lines: `enforce_rbac`, `admin_listen`

Inside such a file, outside `#` / `//` comments, we flag:

1. Any line that sets RBAC off:
   - `enforce_rbac\s*=\s*off`
   - `KONG_ENFORCE_RBAC\s*[:=]\s*"?off"?`
   - `--set enforce_rbac=off` (Helm)
2. `KONG_ADMIN_LISTEN` / `admin_listen` that binds `0.0.0.0:` (any
   port) **and** the same file does NOT enable RBAC anywhere
   (`enforce_rbac = on` / `KONG_ENFORCE_RBAC=on`) AND does not set
   `KONG_ADMIN_GUI_AUTH` to a real strategy
   (`basic-auth`/`key-auth`/`ldap-auth-advanced`/`openid-connect`).
3. Helm `values.yaml` `admin: { enabled: true, http: { enabled: true } }`
   without `enterprise.rbac.enabled: true` in the same document.

Each occurrence emits one finding line.

Stdlib-only.

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List


_KONG_IMAGE = re.compile(r"""\bkong(?:/kong-gateway)?:(?:\d|latest)""")
_KONG_HELM_CHART = re.compile(r"""\bkong/kong\b""")
_KONG_ENV_HINT = re.compile(
    r"""\b(?:KONG_ADMIN_LISTEN|KONG_ENFORCE_RBAC|KONG_ADMIN_GUI_AUTH|admin_listen|enforce_rbac)\b"""
)

_RBAC_OFF_KCONF = re.compile(r"""^\s*enforce_rbac\s*=\s*off\b""", re.IGNORECASE)
_RBAC_OFF_ENV = re.compile(
    r"""\bKONG_ENFORCE_RBAC\b\s*[:=]\s*["']?off["']?""", re.IGNORECASE
)
_RBAC_OFF_HELM = re.compile(
    r"""--set\s+(?:enterprise\.)?rbac\.enabled\s*=\s*false""", re.IGNORECASE
)
_RBAC_OFF_HELM2 = re.compile(
    r"""--set\s+enforce_rbac\s*=\s*off""", re.IGNORECASE
)

_RBAC_ON_KCONF = re.compile(r"""^\s*enforce_rbac\s*=\s*on\b""", re.IGNORECASE)
_RBAC_ON_ENV = re.compile(
    r"""\bKONG_ENFORCE_RBAC\b\s*[:=]\s*["']?on["']?""", re.IGNORECASE
)
_HELM_RBAC_ENABLED_TRUE = re.compile(
    r"""^\s*rbac\s*:\s*\n\s*enabled\s*:\s*true""", re.MULTILINE
)
# Looser: "enabled: true" within an enterprise.rbac block (single-line check).
_HELM_RBAC_INLINE_TRUE = re.compile(
    r"""(?:enterprise\.)?rbac\.enabled\s*[:=]\s*true""", re.IGNORECASE
)

_ADMIN_LISTEN_PUBLIC_KCONF = re.compile(
    r"""^\s*admin_listen\s*=\s*["']?0\.0\.0\.0:(\d+)""", re.IGNORECASE
)
_ADMIN_LISTEN_PUBLIC_ENV = re.compile(
    r"""\bKONG_ADMIN_LISTEN\b\s*[:=]\s*["']?0\.0\.0\.0:(\d+)""", re.IGNORECASE
)

_GUI_AUTH_STRATEGY = re.compile(
    r"""\bKONG_ADMIN_GUI_AUTH\b\s*[:=]\s*["']?(basic-auth|key-auth|ldap-auth-advanced|openid-connect)\b""",
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


def _is_kong_file(text: str) -> bool:
    if _KONG_IMAGE.search(text):
        return True
    if _KONG_ENV_HINT.search(text):
        return True
    if _KONG_HELM_CHART.search(text):
        return True
    return False


def _has_rbac_enabled(text: str) -> bool:
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)
        if _RBAC_ON_KCONF.match(line) or _RBAC_ON_ENV.search(line):
            return True
        if _HELM_RBAC_INLINE_TRUE.search(line):
            return True
    if _HELM_RBAC_ENABLED_TRUE.search(text):
        return True
    return False


def _has_gui_auth_strategy(text: str) -> bool:
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)
        if _GUI_AUTH_STRATEGY.search(line):
            return True
    return False


_K8S_ENV_NAME_VALUE = re.compile(
    r"""-\s*name\s*:\s*["']?(KONG_[A-Z_]+)["']?\s*\n\s*value\s*:\s*["']?([^"'\n]+)["']?""",
    re.MULTILINE,
)


def _expand_k8s_env(text: str) -> str:
    """Inline k8s env name/value pairs as KONG_FOO=value lines so the
    line-based scanners can find them. Appends synthetic lines, preserving
    original line numbers for unrelated content."""
    extras = []
    for m in _K8S_ENV_NAME_VALUE.finditer(text):
        extras.append(f"{m.group(1)}={m.group(2)}")
    if not extras:
        return text
    return text + "\n# __synthetic_k8s_env__\n" + "\n".join(extras) + "\n"


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if not _is_kong_file(text):
        return findings

    # Expand k8s env name/value pairs so single-line regexes can match.
    expanded = _expand_k8s_env(text)
    rbac_enabled = _has_rbac_enabled(expanded)
    gui_auth = _has_gui_auth_strategy(expanded)

    for lineno, raw in enumerate(expanded.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        # Rule 1: explicit RBAC off.
        if _RBAC_OFF_KCONF.match(line):
            findings.append(
                f"{path}:{lineno}: kong.conf sets enforce_rbac = off "
                f"(CWE-306/CWE-732): {raw.strip()[:160]}"
            )
            continue
        if _RBAC_OFF_ENV.search(line):
            findings.append(
                f"{path}:{lineno}: KONG_ENFORCE_RBAC=off disables Admin "
                f"API RBAC (CWE-306/CWE-732): {raw.strip()[:160]}"
            )
            continue
        if _RBAC_OFF_HELM.search(line) or _RBAC_OFF_HELM2.search(line):
            findings.append(
                f"{path}:{lineno}: helm install disables Kong RBAC "
                f"(CWE-306/CWE-732): {raw.strip()[:160]}"
            )
            continue

        # Rule 2: admin API on 0.0.0.0 with no RBAC + no GUI auth strategy.
        if (not rbac_enabled) and (not gui_auth):
            m = _ADMIN_LISTEN_PUBLIC_KCONF.match(line) or _ADMIN_LISTEN_PUBLIC_ENV.search(line)
            if m:
                findings.append(
                    f"{path}:{lineno}: kong Admin API bound to 0.0.0.0:"
                    f"{m.group(1)} with no RBAC enforcement and no GUI "
                    f"auth strategy (CWE-306/CWE-732): "
                    f"{raw.strip()[:160]}"
                )
                continue
    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "kong.conf",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".tf",
    ".tpl", ".env", ".conf",
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

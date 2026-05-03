#!/usr/bin/env python3
"""
llm-output-emqx-allow-anonymous-true-detector

Flags **EMQX** MQTT broker configurations that allow anonymous client
connections, i.e. any TCP client can publish/subscribe without
presenting credentials.

EMQX exposes anonymous-access through a few surfaces:

- Classic config (`emqx.conf`, HOCON): `allow_anonymous = true`
- New-style HOCON: `mqtt.allow_anonymous = true`
- Authentication chain: `authentication = []` (empty list disables
  all authenticators -> all clients accepted)
- Env var override: `EMQX_ALLOW_ANONYMOUS=true`,
  `EMQX_MQTT__ALLOW_ANONYMOUS=true`
- Helm `values.yaml`: `emqxConfig.EMQX_ALLOW_ANONYMOUS: "true"`

Maps to:
- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource
- CWE-285: Improper Authorization (when paired with the default
  ACL `allow all`)

LLMs reach for anonymous EMQX because every "first MQTT in 5 minutes"
walkthrough sets `allow_anonymous = true` so that `mosquitto_pub` /
`mosquitto_sub` "just work" against the broker.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
*.conf, *.hocon, *.yaml, *.yml, *.toml, Dockerfile, docker-compose.*,
*.sh, *.bash, *.service, *.env-style fixtures named *.envconf or
similar -- we DO NOT pick up real `.env` files because the repo
guardrail forbids them).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
Outside `#` / `//` comments, we flag any of:

1. `allow_anonymous = true` / `allow_anonymous: true`
2. `mqtt.allow_anonymous = true` (dotted HOCON key)
3. `EMQX_ALLOW_ANONYMOUS=true` and `EMQX_MQTT__ALLOW_ANONYMOUS=true`
4. `authentication = []` or `authentication: []` (empty list disables
   the authenticator chain in EMQX 5.x)
5. Helm-style nested map:
       emqxConfig:
         EMQX_ALLOW_ANONYMOUS: "true"

Boolean parsing accepts `true`, `True`, `TRUE`, and quoted `"true"`
/ `'true'`.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_TRUE_RX = r"""(?:"true"|'true'|true|True|TRUE)"""

# allow_anonymous on its own line.
_ALLOW_ANON = re.compile(
    rf"""\ballow_anonymous\s*[:=]\s*{_TRUE_RX}(?![A-Za-z0-9_])"""
)

# mqtt.allow_anonymous (dotted HOCON).
_MQTT_ALLOW_ANON = re.compile(
    rf"""\bmqtt\.allow_anonymous\s*[:=]\s*{_TRUE_RX}(?![A-Za-z0-9_])"""
)

# Env var forms (also used in compose `environment:` blocks).
# EMQX 5.x convention uses `__` as the dotted-key separator, so
# `mqtt.allow_anonymous` becomes `EMQX_MQTT__ALLOW_ANONYMOUS`, while
# the legacy short form is just `EMQX_ALLOW_ANONYMOUS`.
_ENV_ALLOW_ANON = re.compile(
    rf"""\bEMQX_(?:MQTT__)?ALLOW_ANONYMOUS\s*[:=]\s*{_TRUE_RX}(?![A-Za-z0-9_])"""
)

# authentication = [] / authentication: []
_EMPTY_AUTH = re.compile(
    r"""\bauthentication\s*[:=]\s*\[\s*\]"""
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []

    # Helm-style nested key: track whether we are inside an
    # `emqxConfig:` (or similar) YAML map and look for
    # EMQX_ALLOW_ANONYMOUS: "true" indented under it.
    lines = text.splitlines()
    for lineno, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        # Use ENV pattern first so it catches the helm nested form too
        # (the key on its own line still matches because we don't
        # require start-of-line for the env regex).
        if _ENV_ALLOW_ANON.search(line):
            findings.append(
                f"{path}:{lineno}: EMQX_ALLOW_ANONYMOUS env/helm "
                f"value set to true (CWE-306/CWE-1188): "
                f"{raw.strip()[:160]}"
            )
            continue

        if _MQTT_ALLOW_ANON.search(line):
            findings.append(
                f"{path}:{lineno}: mqtt.allow_anonymous = true "
                f"(CWE-306/CWE-1188, MQTT broker accepts unauthenticated "
                f"clients): {raw.strip()[:160]}"
            )
            continue

        if _ALLOW_ANON.search(line):
            findings.append(
                f"{path}:{lineno}: allow_anonymous = true "
                f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
            continue

        if _EMPTY_AUTH.search(line):
            findings.append(
                f"{path}:{lineno}: authentication = [] disables EMQX "
                f"authenticator chain (CWE-306/CWE-285, all clients "
                f"accepted): {raw.strip()[:160]}"
            )
            continue

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "emqx.conf",
)
_TARGET_EXTS = (
    ".conf", ".hocon", ".yaml", ".yml", ".toml",
    ".sh", ".bash", ".service", ".envconf", ".dockerfile",
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

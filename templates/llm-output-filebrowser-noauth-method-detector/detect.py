#!/usr/bin/env python3
"""
llm-output-filebrowser-noauth-method-detector

Flags File Browser (filebrowser/filebrowser) configurations that
disable login by selecting the `noauth` authentication method or by
passing the `--noauth` CLI flag. File Browser exposes a full HTTP
file manager (browse, upload, download, rename, share, execute
configured commands) over its `address:port`. With `auth.method =
noauth` every visitor inherits the configured "anonymous" user, which
in the documented quick-start ships with full read/write on the
served root and with the `commands` allowlist defaulting to empty
but routinely widened to `["git","sh","bash"]` by users who want to
trigger pulls from the UI. Anonymous access combined with a non-
empty `commands` list is unauthenticated remote command execution.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-284: Improper Access Control.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
.filebrowser.json, filebrowser.json, settings.json, *.json, *.yaml,
*.yml, *.conf, *.ini, *.sh, *.bash, *.service, *.env, Dockerfile,
docker-compose.*).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag, outside `#` / `;` / `//` comment lines, any of:

1. JSON / YAML directive that sets the auth method to `noauth`:
   `"auth.method": "noauth"`, `"auth": {"method": "noauth"}`, or
   YAML `auth:\n  method: noauth`. (File Browser also accepts the
   short form `"method": "noauth"` inside an `auth` block.)
2. CLI flag `--noauth` to a `filebrowser` invocation (Dockerfile
   CMD/ENTRYPOINT, shell script, systemd ExecStart, k8s args).
3. `filebrowser config init --auth.method=noauth` or
   `filebrowser config set --auth.method noauth` in setup scripts.
4. Env-var override `FB_AUTH_METHOD=noauth` (used by
   filebrowser/filebrowser container image and several community
   Helm charts).
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# JSON: "auth.method": "noauth"  OR  "method": "noauth"
_JSON_AUTH_METHOD_NOAUTH = re.compile(
    r'''(?im)"(?:auth\.method|method)"\s*:\s*"noauth"'''
)

# YAML: method: noauth (inside or outside an auth: block — we accept
# either; combined with the file-name heuristic this is specific
# enough for filebrowser configs).
_YAML_METHOD_NOAUTH = re.compile(
    r'''(?im)^\s*(?:auth\.)?method\s*:\s*["']?noauth["']?\s*(?:#.*)?$'''
)

# CLI: filebrowser ... --noauth (shell form OR JSON exec array form,
# e.g. CMD ["filebrowser","--root","/srv","--noauth"]).
_CLI_NOAUTH = re.compile(
    r'''(?im)(?:^|[\s\["'])filebrowser\b[^\n#;]*?--noauth\b'''
)

# CLI: filebrowser config (init|set) --auth.method=noauth (or space)
_CLI_CONFIG_NOAUTH = re.compile(
    r'''(?im)filebrowser\s+config\s+(?:init|set)\b[^\n#;]*?--auth\.method[=\s]+["']?noauth["']?'''
)

# Env-var override
_ENV_FB_AUTH_NOAUTH = re.compile(
    r'''(?im)^\s*(?:export\s+|-\s+)?FB_AUTH_METHOD\s*[:=]\s*["']?noauth["']?\b'''
)

_COMMENT_LINE = re.compile(r"^\s*(?:#|;|//)")


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        if _JSON_AUTH_METHOD_NOAUTH.search(raw):
            findings.append(
                f"{path}:{lineno}: filebrowser config sets "
                f"`auth.method = noauth` — every visitor inherits the "
                f"anonymous user with full file-manager access "
                f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
            continue

        if _YAML_METHOD_NOAUTH.search(raw):
            findings.append(
                f"{path}:{lineno}: filebrowser YAML sets auth method "
                f"to `noauth` — login is disabled "
                f"(CWE-306/CWE-284): {raw.strip()[:160]}"
            )
            continue

        if _CLI_NOAUTH.search(raw):
            findings.append(
                f"{path}:{lineno}: `filebrowser ... --noauth` flag "
                f"disables authentication on the file manager "
                f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
            continue

        if _CLI_CONFIG_NOAUTH.search(raw):
            findings.append(
                f"{path}:{lineno}: `filebrowser config` invocation "
                f"persists `auth.method=noauth` into the settings DB "
                f"(CWE-306/CWE-284): {raw.strip()[:160]}"
            )
            continue

        if _ENV_FB_AUTH_NOAUTH.search(raw):
            findings.append(
                f"{path}:{lineno}: FB_AUTH_METHOD=noauth env override "
                f"templates the filebrowser config with login "
                f"disabled (CWE-306/CWE-284): {raw.strip()[:160]}"
            )
            continue

    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".filebrowser.json",
    "filebrowser.json",
    "settings.json",
)
_TARGET_EXTS = (
    ".json", ".yaml", ".yml", ".conf", ".ini", ".sh", ".bash",
    ".service", ".tpl", ".env",
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

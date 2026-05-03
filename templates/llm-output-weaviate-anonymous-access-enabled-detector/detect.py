#!/usr/bin/env python3
"""
llm-output-weaviate-anonymous-access-enabled-detector

Flags Weaviate vector-database deployments that enable
`AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true` *and* do not enable
any other authentication module (API key, OIDC). With anonymous
access on and no auth, every REST/GraphQL endpoint is reachable
without credentials, including endpoints that mutate the schema
and the vector store.

Why LLMs reach for this
-----------------------
The official Weaviate quickstart docker-compose ships with:

    AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'

so the embedded "Try it out" example works out of the box. LLMs
copy that exact block when asked for "a docker-compose to run
Weaviate locally" and the user then deploys it to a public host.
The result is a public Weaviate with `Admin` privileges available
to anyone who can reach port 8080.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-1188: Insecure Default Initialization of Resource.

Heuristic
---------
We flag, outside `#` / `//` comments, any line that sets
`AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED` to a truthy value
(`true`, `True`, `1`, `yes`, `on`) when the same file does *not*
also enable one of the auth modules:

    AUTHENTICATION_APIKEY_ENABLED=true
    AUTHENTICATION_OIDC_ENABLED=true

Forms recognized:
1. YAML / Compose `KEY: value` and `KEY: 'value'`.
2. Env-file / shell `KEY=value` and `export KEY=value`.
3. Helm CLI `--set ...AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true`.
4. Helm values nested form `authentication: { anonymous_access: { enabled: true } }`.

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks *.yml, *.yaml, *.env, .env*, *.sh, *.bash, Dockerfile,
docker-compose*, *.tf, *.conf).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_TRUTHY = {"true", "1", "yes", "on"}

# Compose / env / helm-set forms for the anonymous flag.
# YAML uses `:`, env/helm-set use `=`.
_ANON = re.compile(
    r"""\bAUTHENTICATION_ANONYMOUS_ACCESS_ENABLED\s*[:=]\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?"""
)

# Same KEY can appear in helm `--set` chains.
_ANON_HELM = re.compile(
    r"""--set\s+(?:[A-Za-z0-9_.-]+\.)?AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED\s*=\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?"""
)

# Helm values nested form. We accept either explicit `enabled: true`
# under an `anonymous_access:` key, on its own line.
_ANON_NESTED = re.compile(
    r"""^\s*enabled\s*:\s*['"]?(?P<val>[A-Za-z0-9]+)['"]?\s*$"""
)

# Auth-module presence markers (file-level, not per-line).
_APIKEY_ON = re.compile(
    r"""\bAUTHENTICATION_APIKEY_ENABLED\s*[:=]\s*['"]?(true|1|yes|on)['"]?""",
    re.IGNORECASE,
)
_OIDC_ON = re.compile(
    r"""\bAUTHENTICATION_OIDC_ENABLED\s*[:=]\s*['"]?(true|1|yes|on)['"]?""",
    re.IGNORECASE,
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


def _has_other_auth(text: str) -> bool:
    # Strip comment-only lines before checking, to avoid being fooled
    # by a commented-out APIKEY_ENABLED line.
    cleaned = []
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        cleaned.append(_strip_comment(raw))
    body = "\n".join(cleaned)
    return bool(_APIKEY_ON.search(body) or _OIDC_ON.search(body))


def _is_truthy(val: str) -> bool:
    return val.lower() in _TRUTHY


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    other_auth = _has_other_auth(text)

    # Track whether we are inside an `anonymous_access:` block, to
    # disambiguate the nested `enabled: true` form.
    in_anon_block = False
    anon_indent = -1

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        # Track YAML nesting for the helm-values form.
        stripped = line.rstrip()
        indent = len(line) - len(line.lstrip(" "))
        if re.match(r"\s*anonymous_access\s*:\s*$", stripped):
            in_anon_block = True
            anon_indent = indent
            continue
        if in_anon_block and stripped and indent <= anon_indent and not stripped.lstrip().startswith("-"):
            # Block ended.
            in_anon_block = False
            anon_indent = -1

        for m in _ANON.finditer(line):
            if _is_truthy(m.group("val")) and not other_auth:
                findings.append(
                    f"{path}:{lineno}: AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED="
                    f"'{m.group('val')}' with no APIKEY/OIDC auth in same file "
                    f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
                )

        for m in _ANON_HELM.finditer(line):
            if _is_truthy(m.group("val")) and not other_auth:
                findings.append(
                    f"{path}:{lineno}: helm --set ANON_ACCESS_ENABLED="
                    f"'{m.group('val')}' with no APIKEY/OIDC enable flag "
                    f"(CWE-306/CWE-1188): {raw.strip()[:160]}"
                )

        if in_anon_block:
            m = _ANON_NESTED.match(line)
            if m and _is_truthy(m.group("val")) and not other_auth:
                findings.append(
                    f"{path}:{lineno}: anonymous_access.enabled="
                    f"'{m.group('val')}' (helm values) with no APIKEY/OIDC "
                    f"in same file (CWE-306/CWE-1188): {raw.strip()[:160]}"
                )

    return findings


_TARGET_NAMES = (
    "dockerfile", ".env",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".env", ".sh", ".bash", ".tf", ".conf", ".tpl",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.endswith(_TARGET_EXTS) or low.startswith(".env"):
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

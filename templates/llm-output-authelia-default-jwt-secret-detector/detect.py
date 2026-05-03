#!/usr/bin/env python3
"""
llm-output-authelia-default-jwt-secret-detector

Flags Authelia configurations that ship with the well-known
placeholder JWT secrets (or sibling secrets `session.secret`,
`storage.encryption_key`) copied verbatim from the upstream example
config / docker-compose tutorials.

Authelia (authelia/authelia, v4.x) signs identity verification JWTs
with `identity_validation.reset_password.jwt_secret` (>=4.38) or
`jwt_secret` (<=4.37). The upstream example
(`internal/configuration/test_resources/config.yml`,
`compose/lite/authelia/configuration.yml`, and various docs pages)
uses placeholder values such as:

    a_very_important_secret
    insecure_secret
    unsecure_session_secret
    a_very_important_session_secret
    you_must_generate_a_random_string_of_more_than_eighty_characters_to_use_here

Anything signed with one of those secrets is forge-able by any party
who has read the public Authelia repo. That is a complete
authentication bypass for the SSO portal.

Maps to:
- CWE-798: Use of Hard-coded Credentials.
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-321: Use of Hard-coded Cryptographic Key.

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks Authelia config files: *.yml, *.yaml, .env, *.env, Dockerfile,
docker-compose.* and Helm template files).

Heuristic
---------
We flag any of the following textual occurrences (outside `#` / `//`
comments):

1. A YAML key `jwt_secret`, `session.secret` / nested `secret:`
   inside a `session:` block, `storage.encryption_key` /
   `encryption_key:` inside a `storage:` block whose value is one
   of the upstream placeholder strings.
2. The same in env-var form: `AUTHELIA_JWT_SECRET=...`,
   `AUTHELIA_SESSION_SECRET=...`,
   `AUTHELIA_STORAGE_ENCRYPTION_KEY=...` matching a placeholder.
3. Any of those keys whose value is empty or shorter than 32 bytes
   (Authelia rejects <32-byte secrets at startup, but LLMs still
   hand them out -- and earlier versions silently accepted them).

Each occurrence emits one finding line.

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# Known placeholder values shipped in the upstream repo / docs.
_PLACEHOLDER_VALUES = {
    "a_very_important_secret",
    "insecure_secret",
    "unsecure_session_secret",
    "a_very_important_session_secret",
    "a_very_important_storage_encryption_key",
    "you_must_generate_a_random_string_of_more_than_eighty_characters_to_use_here",
    "changeme",
    "change_me",
    "secret",
    "supersecret",
    "your_jwt_secret",
    "your_session_secret",
}

_KEY_NAMES = (
    "jwt_secret",
    "encryption_key",
    "session_secret",
)

# Match a YAML scalar assignment for one of the dangerous keys.
# Captures the value (quoted or bare) on the same line.
_YAML_KV = re.compile(
    r"""^\s*(jwt_secret|encryption_key|secret)\s*:\s*(?:(['"])(.*?)\2|(\S.*?))\s*(?:#.*)?$"""
)

# Env-var form (.env, Dockerfile ENV, compose environment list).
_ENV_KV = re.compile(
    r"""\bAUTHELIA_(?:IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET|JWT_SECRET|SESSION_SECRET|STORAGE_ENCRYPTION_KEY)\s*[:=]\s*(?:(['"])(.*?)\1|(\S.*))$"""
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")

# Track a tiny bit of YAML context so we can attribute a bare
# `secret:` to either `session:` or another block. We keep this very
# shallow: we only remember the most recent top-level key.
_TOP_LEVEL_KEY = re.compile(r"""^([a-z_]+)\s*:\s*(?:#.*)?$""")


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


def _classify(key: str, value: str, top_block: str) -> str | None:
    """Return a CWE label if (key,value,context) is dangerous."""
    v = value.strip().strip("'\"")
    if not v:
        # Empty secret. Authelia would refuse to start in modern
        # versions, but LLMs still emit this and older releases let
        # it pass.
        return f"empty {key} (CWE-1188)"
    if v.lower() in _PLACEHOLDER_VALUES:
        return f"placeholder value '{v[:48]}' for {key} (CWE-798/CWE-321)"
    # `secret:` is only meaningful when nested under `session:`,
    # `storage:` or `notifier.smtp:` -- we only flag it when we are
    # currently under `session:` or `storage:`.
    if key == "secret" and top_block not in ("session", "storage", "notifier"):
        return None
    if len(v) < 32 and key in ("jwt_secret", "encryption_key") or (
        key == "secret" and top_block in ("session", "storage") and len(v) < 32
    ):
        return f"short {key} ({len(v)} bytes < 32) (CWE-321/CWE-1188)"
    return None


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    top_block = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        m_top = _TOP_LEVEL_KEY.match(line)
        if m_top and not line.startswith(" "):
            top_block = m_top.group(1)
            continue

        m = _YAML_KV.match(line)
        if m:
            key = m.group(1)
            value = m.group(3) if m.group(3) is not None else (m.group(4) or "")
            label = _classify(key, value, top_block)
            if label:
                findings.append(
                    f"{path}:{lineno}: authelia config: {label}: "
                    f"{raw.strip()[:160]}"
                )
                continue

        m_env = _ENV_KV.search(line)
        if m_env:
            value = m_env.group(2) if m_env.group(2) is not None else (m_env.group(3) or "")
            v = value.strip().strip("'\"")
            if not v:
                findings.append(
                    f"{path}:{lineno}: authelia env var has empty secret "
                    f"(CWE-1188): {raw.strip()[:160]}"
                )
                continue
            if v.lower() in _PLACEHOLDER_VALUES:
                findings.append(
                    f"{path}:{lineno}: authelia env var uses placeholder "
                    f"'{v[:48]}' (CWE-798/CWE-321): {raw.strip()[:160]}"
                )
                continue
            if len(v) < 32:
                findings.append(
                    f"{path}:{lineno}: authelia env var secret too short "
                    f"({len(v)} bytes < 32) (CWE-321/CWE-1188): "
                    f"{raw.strip()[:160]}"
                )
                continue
    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "configuration.yml",
    "configuration.yaml",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".env", ".env.example", ".tpl",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile") or low.endswith(_TARGET_EXTS):
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

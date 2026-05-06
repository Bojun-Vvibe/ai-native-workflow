#!/usr/bin/env python3
"""
llm-output-outline-secret-key-default-detector

Flags **Outline** (the open-source team wiki / knowledge base by
outline.com — *not* the Outline VPN client) deployments where
`SECRET_KEY` or `UTILS_SECRET` is left at the upstream `.env.sample`
placeholder, an empty string, or an obvious weak literal.

Why it matters
--------------
Outline's `SECRET_KEY` is used to sign / encrypt user session
cookies and a handful of internal HMAC tokens. `UTILS_SECRET` is
used as the shared secret for internal `/api/utils.*` endpoints
(notably `utils.gc` for the OCR/file pipeline) which Outline
trusts as if they came from itself.

If the attacker knows `SECRET_KEY` they can forge a session cookie
for any user (including the workspace admin) and read or rewrite
every doc in the workspace. If they know `UTILS_SECRET` they can
hit internal-only endpoints that bypass the regular ACL layer.

The upstream `.env.sample` ships with this exact text:

    # Generate a hex-encoded 32-byte random key. You should use
    # `openssl rand -hex 32` in your terminal to generate a random
    # value.
    SECRET_KEY=generate_a_new_key
    UTILS_SECRET=generate_a_new_key

Both literals appear verbatim in copy-pasted "deploy outline in 5
minutes" tutorials and LLM completions.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-330: Use of Insufficiently Random Values
  - CWE-1188: Insecure Default Initialization of Resource
  - CWE-384: Session Fixation (downstream: forged session cookies)
  - OWASP A02:2021 Cryptographic Failures
  - OWASP A05:2021 Security Misconfiguration
  - OWASP A07:2021 Identification & Authentication Failures

Heuristic
---------
In `outline*`-named files, `*.env*`, `docker-compose.*`,
`*.y*ml`, `*.conf`, `*.sh`, `Dockerfile*`, `*.toml`, `*.json`, and
any file whose body matches Outline scope hints
(`outlinewiki/outline`, `getoutline/outline`, `OUTLINE_`,
`utils.gc`), we flag:

1. `SECRET_KEY=<weak>` / `SECRET_KEY: <weak>` (env or YAML form)
2. `UTILS_SECRET=<weak>` / `UTILS_SECRET: <weak>`

where `<weak>` is one of:

  * empty
  * `generate_a_new_key` (upstream literal)
  * `change_me`, `changeme`, `change-me`, `changeit`
  * `secret`, `password`, `default`, `test`, `demo`, `example`
  * `outline`, `key`, `secretkey`, `secret_key`, `utils_secret`
  * `12345*`, `qwerty`, `letmein`, `admin`
  * any value < 64 hex chars (Outline docs require
    `openssl rand -hex 32`, i.e. 64 hex chars; we approximate
    via length only).

To avoid colliding with other apps' SECRET_KEY (Django, Flask,
etc.), we ONLY flag when the file is in Outline scope.

We do NOT flag:

  * `${...}` / `{{ ... }}` template references.
  * Long high-entropy values (>= 64 chars).
  * `.md` / `.rst` / `.txt` / `.adoc` prose.
  * Files with no Outline scope hint (so a generic `SECRET_KEY=foo`
    in a Django settings.py is left alone).

Stdlib-only. Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_OUTLINE_SCOPE_HINTS = (
    "outlinewiki/outline",
    "getoutline/outline",
    "outline-wiki",
    "outline_wiki",
    "outline:",
    "url=https://wiki",   # benign; not used to scope, kept for noise floor
    "utils_secret",
    "utils.gc",
    "outline_url",
    "slack_app_id",  # outline-specific env (when present near SECRET_KEY)
    "default_language=en_us",  # outline default in .env.sample
)

# To reduce false positives we also check for the env-var pair: a
# file qualifies if it contains ANY of these tokens.

_KEY_RE = re.compile(
    r"""(?P<key>SECRET_KEY|UTILS_SECRET)\s*[:=]\s*
        (?:"(?P<dval>[^"\n]*)"
          |'(?P<sval>[^'\n]*)'
          |(?P<bval>[^"'\s,}#\n]*))""",
    re.VERBOSE,
)

_WEAK_LITERALS = {
    "",
    "generate_a_new_key", "generate-a-new-key", "generateanewkey",
    "your_random_string", "your-random-string",
    "change_me", "changeme", "change-me", "changeit",
    "secret", "password", "passwd", "pass",
    "default", "test", "demo", "example",
    "outline", "key", "secretkey", "secret_key",
    "utils_secret", "utilssecret",
    "12345", "123456", "1234567", "12345678", "123456789",
    "qwerty", "letmein", "admin", "root",
}

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")
_PROSE_EXTS = (".md", ".rst", ".txt", ".adoc")


def _is_template_ref(v: str) -> bool:
    return "${" in v or v.startswith("$") or "{{" in v


def _file_in_scope(text: str, path: str) -> bool:
    base = os.path.basename(path).lower()
    if "outline" in base:
        return True
    low = text.lower()
    return any(h in low for h in _OUTLINE_SCOPE_HINTS)


def _classify(val: str) -> str:
    v = val.strip().strip('"').strip("'")
    if _is_template_ref(v):
        return "ok"
    if v.lower() in _WEAK_LITERALS:
        return "weak"
    if len(v) < 64:
        return "short"
    return "ok"


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    base = os.path.basename(path).lower()
    if base.endswith(_PROSE_EXTS):
        return []
    if not _file_in_scope(text, path):
        return []

    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = raw.split("#", 1)[0]
        for m in _KEY_RE.finditer(line):
            key = m.group("key")
            val = m.group("dval") or m.group("sval") or m.group("bval") or ""
            kind = _classify(val)
            if kind == "weak":
                if key == "SECRET_KEY":
                    findings.append(
                        f"{path}:{lineno}: outline {key} = placeholder "
                        f"{val!r} -> session cookies / internal HMACs "
                        f"are signed with a known value; attacker can "
                        f"forge a session cookie for any user including "
                        f"the workspace admin (CWE-798/CWE-1392/"
                        f"CWE-384): {raw.strip()[:160]}"
                    )
                else:
                    findings.append(
                        f"{path}:{lineno}: outline {key} = placeholder "
                        f"{val!r} -> internal `/api/utils.*` endpoints "
                        f"trust this shared secret; attacker can hit "
                        f"`utils.gc` and other ACL-bypassing endpoints "
                        f"(CWE-798/CWE-1392): {raw.strip()[:160]}"
                    )
            elif kind == "short":
                findings.append(
                    f"{path}:{lineno}: outline {key} is "
                    f"{len(val.strip())} chars (< 64) -> Outline docs "
                    f"require `openssl rand -hex 32` (64 hex chars); "
                    f"this value is well below the recommended entropy "
                    f"floor (CWE-330): {raw.strip()[:160]}"
                )
    return findings


_TARGET_EXTS = (
    ".conf", ".yaml", ".yml", ".ini", ".env", ".env.example",
    ".env.sample", ".sh", ".bash", ".dockerfile", ".toml", ".json",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if (
                        "outline" in low
                        or low.startswith("dockerfile")
                        or low.startswith("docker-compose")
                        or low.endswith(_TARGET_EXTS)
                    ):
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

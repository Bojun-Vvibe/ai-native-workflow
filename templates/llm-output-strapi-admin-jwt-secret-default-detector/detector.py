#!/usr/bin/env python3
"""Detect Strapi configuration snippets emitted by LLMs that ship the
default ``admin.auth.secret`` (or other Strapi secrets) as a literal
quickstart placeholder.

Strapi v4/v5 expects four secrets to be set per-environment:

  - ``admin.auth.secret``                 (admin JWT signing key)
  - ``api.token.salt``                    (API token signing salt)
  - ``app.keys``                          (session signing keys, list)
  - ``users-permissions``                 ``jwtSecret`` (end-user JWT)

The official quickstart and many tutorials demo these with literal
placeholder strings. LLMs frequently paste those literals into a
``config/admin.js``, ``config/server.js``, or ``.env`` example.
Once the resulting Strapi instance is online, anyone who knows the
placeholder can mint admin or user JWTs and take the panel over.

Patterns flagged:

  1. ``admin.auth.secret``-style assignment with a known placeholder
     value (``tobemodified``, ``changeme``, ``please-change-me``,
     ``replaceme``, ``yourSecretKey``, ``mySecret``, ``secretKey``,
     ``somethingSecret``, ``aSecretSalt``, ``myJwtSecret``,
     ``test``, ``secret``).
  2. ``.env``-style ``ADMIN_JWT_SECRET=<placeholder>`` /
     ``API_TOKEN_SALT=...`` / ``JWT_SECRET=...`` / ``APP_KEYS=...``.
  3. ``users-permissions`` plugin config with
     ``jwtSecret: '<placeholder>'``.
  4. ``app.keys`` set to an empty list / placeholder list
     (``["toBeModified1", "toBeModified2"]``).

Suppression: a top-level ``# strapi-default-secret-ok`` comment in
the file disables all rules (e.g. an example in onboarding docs).

Public API:
    detect(text: str) -> bool
    scan(text: str)   -> list[(line, reason)]

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "strapi-default-secret-ok"

# Case-insensitive set of known placeholder values that appear in the
# Strapi quickstart, tutorials, and stack-overflow answers.
PLACEHOLDERS = {
    "tobemodified",
    "tobemodified1",
    "tobemodified2",
    "tobemodified3",
    "tobemodified4",
    "changeme",
    "change-me",
    "change_me",
    "please-change-me",
    "pleasechangeme",
    "replaceme",
    "replace-me",
    "yoursecretkey",
    "your-secret-key",
    "your_secret_key",
    "mysecret",
    "my-secret",
    "my_secret",
    "secretkey",
    "secret-key",
    "secret_key",
    "somethingsecret",
    "asecretsalt",
    "asalt",
    "myjwtsecret",
    "jwtsecret",
    "test",
    "secret",
    "supersecret",
    "supersecretkey",
    "default",
    "example",
    "examplekey",
    "placeholder",
    "xxxxx",
    "xxxx",
    "xxx",
    "todo",
}


def _is_placeholder(val: str) -> bool:
    v = val.strip().strip("\"'`").lower()
    if not v:
        return True
    # Strip common wrapping like env-substitution defaults: ${X:-...}.
    # We only check the literal value the LLM produced, so leave as-is.
    return v in PLACEHOLDERS


def _strip_comments(text: str) -> str:
    """Strip ``#`` and ``//`` comments while preserving line numbers.

    Strapi configs are JS / JSON / TOML / .env so we handle both
    comment styles. ``//`` inside a quoted string is preserved.
    """
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        nl = "\n" if line.endswith("\n") else ""
        if stripped.startswith("#") or stripped.startswith("//"):
            out.append(nl)
            continue
        # Inline comment handling: walk the line tracking quotes.
        in_quote = None
        cut = -1
        i = 0
        while i < len(line):
            ch = line[i]
            if in_quote:
                if ch == "\\" and i + 1 < len(line):
                    i += 2
                    continue
                if ch == in_quote:
                    in_quote = None
                i += 1
                continue
            if ch in "\"'`":
                in_quote = ch
                i += 1
                continue
            if ch == "#" and (i == 0 or line[i - 1].isspace()):
                cut = i
                break
            if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                cut = i
                break
            i += 1
        if cut >= 0:
            out.append(line[:cut].rstrip() + nl)
        else:
            out.append(line)
    return "".join(out)


# Rule 1 / 3: object-style ``secret: 'value'`` for the known keys.
#
# Matches things like:
#   secret: 'tobemodified'
#   secret: env('ADMIN_JWT_SECRET', 'tobemodified')
#   jwtSecret: 'changeme'
_OBJ_KEY_NAMES = (
    "secret",
    "jwtSecret",
    "salt",
)

_OBJ_ASSIGN_RE = re.compile(
    r"""(?ix)
    \b
    (?P<key> secret | jwtSecret | salt )
    \s* : \s*
    (?:
        env \s* \( \s*
        (?: ['"][^'"]+['"] )
        (?: \s* , \s* (?P<envdef> ['"][^'"]*['"] ) )?
        \s* \)
        |
        (?P<lit> ['"][^'"]*['"] )
    )
    """,
)

# Rule 2: env-style ``KEY=VALUE`` on a single line.
_ENV_KEYS = (
    "ADMIN_JWT_SECRET",
    "API_TOKEN_SALT",
    "JWT_SECRET",
    "APP_KEYS",
    "TRANSFER_TOKEN_SALT",
)
_ENV_ASSIGN_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?:export\s+)?
    (?P<key> ADMIN_JWT_SECRET | API_TOKEN_SALT | JWT_SECRET | APP_KEYS | TRANSFER_TOKEN_SALT )
    \s* = \s*
    (?P<val> .* )
    \s* $
    """,
    re.MULTILINE,
)

# Rule 4: ``app.keys`` set to a list literal that looks placeholder-y.
_APP_KEYS_RE = re.compile(
    r"""(?ix)
    \b keys \b
    \s* : \s*
    (?:
        env\.array \s* \( \s*
        (?: ['"][^'"]+['"] )
        (?: \s* , \s* \[ (?P<arrdef> [^\]]* ) \] )?
        \s* \)
        |
        \[ (?P<arrlit> [^\]]* ) \]
    )
    """,
)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _list_is_placeholder(inner: str) -> bool:
    items = [
        x.strip().strip("\"'`")
        for x in inner.split(",")
        if x.strip()
    ]
    if not items:
        return True
    return all(_is_placeholder(x) for x in items)


def scan(text: str) -> list[tuple[int, str]]:
    if SUPPRESS in text:
        return []
    cleaned = _strip_comments(text)
    findings: list[tuple[int, str]] = []

    # Rule 1 / 3: object-style assignments.
    for m in _OBJ_ASSIGN_RE.finditer(cleaned):
        lit = m.group("lit") or m.group("envdef")
        if lit is None:
            continue
        if _is_placeholder(lit):
            findings.append(
                (
                    _line_of(cleaned, m.start()),
                    f"Strapi {m.group('key')!s} set to placeholder value {lit!s} - regenerate per environment",
                )
            )

    # Rule 2: env-file assignments.
    for m in _ENV_ASSIGN_RE.finditer(cleaned):
        key = m.group("key")
        val = m.group("val").strip()
        # Strip surrounding quotes for inspection but keep original
        # for reporting.
        inspect = val.strip("\"'`")
        if key == "APP_KEYS":
            # Comma-separated list.
            if _list_is_placeholder(inspect):
                findings.append(
                    (
                        _line_of(cleaned, m.start()),
                        f"{key} env value {val!s} is all placeholder(s) - regenerate with `openssl rand -base64 32` per key",
                    )
                )
        else:
            if _is_placeholder(inspect):
                findings.append(
                    (
                        _line_of(cleaned, m.start()),
                        f"{key} env value {val!s} is a placeholder - regenerate per environment",
                    )
                )

    # Rule 4: app.keys list literal.
    for m in _APP_KEYS_RE.finditer(cleaned):
        inner = m.group("arrlit") or m.group("arrdef") or ""
        if _list_is_placeholder(inner):
            findings.append(
                (
                    _line_of(cleaned, m.start()),
                    "app.keys list is empty/placeholder - regenerate two distinct random keys",
                )
            )

    findings.sort(key=lambda t: t[0])
    return findings


def detect(text: str) -> bool:
    return bool(scan(text))


def _cli(argv: list[str]) -> int:
    if not argv:
        text = sys.stdin.read()
        hits = scan(text)
        for ln, reason in hits:
            print(f"<stdin>:{ln}: {reason}")
        return 1 if hits else 0

    files_with_hits = 0
    for arg in argv:
        p = Path(arg)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            print(f"{arg}: cannot read: {e}", file=sys.stderr)
            files_with_hits += 1
            continue
        hits = scan(text)
        if hits:
            files_with_hits += 1
            for ln, reason in hits:
                print(f"{arg}:{ln}: {reason}")
    return files_with_hits


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))

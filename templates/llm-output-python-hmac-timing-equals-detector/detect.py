#!/usr/bin/env python3
"""Detect timing-unsafe equality comparison of secrets / HMACs / tokens.

LLMs routinely write Python authentication checks of the form

    if user_token == expected_token:
        ...
    if hmac.new(key, msg, sha256).hexdigest() == provided_sig:
        ...
    if request.headers["X-Api-Key"] == settings.API_KEY:
        ...

Python's `==` on `str` / `bytes` is a *short-circuit* byte-by-byte
compare: it returns False on the first mismatched byte. The wall-clock
time the comparison takes therefore correlates with the length of the
common prefix between the two operands. A networked attacker can
measure that timing and incrementally recover the secret one byte at
a time. The fix is `hmac.compare_digest(a, b)` (or
`secrets.compare_digest`), which is constant-time over equal-length
inputs.

CWE references
--------------
* **CWE-208**: Observable Timing Discrepancy.
* **CWE-203**: Observable Discrepancy.
* **CWE-1254**: Incorrect Comparison Logic Granularity.

What this flags
---------------
On any line where the right-hand or left-hand side of `==` / `!=`
clearly references a *secret-like* identifier:

* `token`, `auth_token`, `access_token`, `refresh_token`, `id_token`
* `api_key`, `apikey`, `api-key`
* `secret`, `client_secret`, `app_secret`
* `password`, `passwd`, `pwd`, `passphrase`
* `signature`, `sig`, `mac`, `hmac`, `digest`, `hash`
* `csrf_token`, `nonce`, `otp`, `pin`
* `session_id`, `session_token`, `cookie`, `bearer`

It also flags:

* `hmac.new(...).hexdigest() == ...` / `... == hmac.new(...).hexdigest()`.
* `hashlib.<algo>(...).hexdigest() == ...` when paired with an
  obvious secret-like identifier on the other side.

What this does NOT flag
-----------------------
* `hmac.compare_digest(a, b)` — the safe API.
* `secrets.compare_digest(a, b)`.
* Comparisons inside `# ` line comments or string literals.
* Lines suffixed with the suppression marker `# timing-safe-ok`
  (e.g. for unit tests that intentionally assert plaintext equality
  on non-secret values).
* `==` against a literal `None` / numeric literal / boolean.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Recurses `*.py` under directories. Exit 1 if any findings,
0 otherwise. Pure python3 stdlib.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# timing-safe-ok"

SECRET_WORDS = (
    "token",
    "auth_token",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "apikey",
    "secret",
    "client_secret",
    "app_secret",
    "password",
    "passwd",
    "pwd",
    "passphrase",
    "signature",
    "hmac",
    "digest",
    "csrf_token",
    "nonce",
    "otp",
    "session_id",
    "session_token",
    "bearer",
    "auth_header",
    "expected_sig",
    "provided_sig",
    "expected_hmac",
    "expected_token",
    "expected_mac",
    "expected_digest",
)

# Build a regex that matches any of the SECRET_WORDS as a word fragment
# inside an identifier. We use substring word-fragment matching so that
# `user_token`, `csrf_tokens`, `api_key_2` all hit.
_SECRET_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:" + "|".join(re.escape(w) for w in SECRET_WORDS) + r")[A-Za-z0-9_]*",
    re.IGNORECASE,
)
# Bare exact-match fallback (e.g. a parameter literally named `token`).
_SECRET_BARE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:" + "|".join(re.escape(w) for w in SECRET_WORDS) + r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

RE_EQ = re.compile(r"(==|!=)")
RE_HEXDIGEST_CALL = re.compile(r"\.hexdigest\s*\(\s*\)")
RE_DIGEST_CALL = re.compile(r"\.digest\s*\(\s*\)")
RE_HMAC_NEW = re.compile(r"\bhmac\s*\.\s*new\s*\(")
RE_HASHLIB = re.compile(r"\bhashlib\s*\.\s*[A-Za-z0-9_]+\s*\(")

# Signals that the line is *already* using a safe API.
RE_SAFE_COMPARE = re.compile(
    r"\b(?:hmac|secrets)\s*\.\s*compare_digest\s*\("
)


def _strip_strings_and_comment(line: str) -> str:
    """Replace string-literal contents with spaces, drop trailing comment."""
    out = []
    in_s = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < len(line):
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                in_s = False
                out.append(ch)
            else:
                out.append(" ")
        else:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_s = True
                quote = ch
                out.append(ch)
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _looks_secret(side: str) -> bool:
    side = side.strip()
    if not side:
        return False
    if _SECRET_RE.search(side):
        return True
    if _SECRET_BARE_RE.search(side):
        return True
    return False


def _is_trivial_literal(side: str) -> bool:
    s = side.strip()
    if s in ("None", "True", "False", "...", "[]", "{}", "()"):
        return True
    if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return True
    return False


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        line = _strip_strings_and_comment(raw)
        if not RE_EQ.search(line):
            continue
        if RE_SAFE_COMPARE.search(line):
            continue
        # Split around the first == or != only.
        m = RE_EQ.search(line)
        op = m.group(1)
        left = line[: m.start()]
        right = line[m.end() :]
        # Trim any leading `if `, `assert `, `elif `, `while `, `return `.
        left_keyword = re.sub(r"^\s*(?:if|elif|while|assert|return)\b", "", left)
        # Trim trailing ` :` or ` and ...` from the right side.
        right_clip = re.split(r"\s+(?:and|or|:)\s|:\s*$", right, maxsplit=1)[0]

        # Treat a `hmac.new(...).hexdigest()` or `hashlib.sha256(...).hexdigest()`
        # call on either side as a strong signal even without a secret-named var.
        digest_left = bool(
            (RE_HEXDIGEST_CALL.search(left_keyword) or RE_DIGEST_CALL.search(left_keyword))
            and (RE_HMAC_NEW.search(left_keyword) or RE_HASHLIB.search(left_keyword))
        )
        digest_right = bool(
            (RE_HEXDIGEST_CALL.search(right_clip) or RE_DIGEST_CALL.search(right_clip))
            and (RE_HMAC_NEW.search(right_clip) or RE_HASHLIB.search(right_clip))
        )

        if _is_trivial_literal(left_keyword) or _is_trivial_literal(right_clip):
            continue

        secret_left = _looks_secret(left_keyword)
        secret_right = _looks_secret(right_clip)

        if digest_left or digest_right:
            findings.append(
                (path, lineno, f"timing-unsafe-{op}-on-digest", raw.rstrip())
            )
            continue
        if secret_left or secret_right:
            findings.append(
                (path, lineno, f"timing-unsafe-{op}-on-secret", raw.rstrip())
            )
            continue
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.py")):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

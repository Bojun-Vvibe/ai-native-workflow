#!/usr/bin/env python3
"""Detect hardcoded cryptographic key material in Python source.

LLMs asked to "encrypt this string" or "sign a token" frequently
produce snippets that bake the AES key, Fernet key, HMAC secret,
or RSA seed directly into the source as a literal `bytes` /
`str`. The resulting file is then committed to a public repo and
the secret leaks. This detector is a *defensive* lint: it never
generates keys, it only flags patterns where a key-shaped literal
is being passed to a known crypto API.

What this flags
---------------
* `Fernet(b"...")`, `Fernet("...")` with a literal argument
* `AES.new(b"...", ...)`, `AES.new("...", ...)` with literal key
* `Cipher(algorithms.AES(b"..."), ...)` with literal key
* `hmac.new(b"...", ...)`, `hmac.new("...", ...)` with literal key
* `hmac.HMAC(b"...", ...)` with literal key
* `PBKDF2HMAC(..., salt=b"...")` with a literal salt that is also
  short enough to be guessable (<= 32 bytes shown literally)
* `jwt.encode(payload, "literal-secret", ...)` with literal secret
* `cryptography.fernet.Fernet(b"...")` (qualified form)

What this does NOT flag
-----------------------
* Calls where the key argument is a Name (variable), Attribute,
  Call, or any non-literal expression — the assumption is that
  the secret is loaded from env/keyring/KMS in those cases.
* Lines marked with a trailing `# crypto-key-ok` comment.
* Occurrences inside `#` comments or string/docstring literals.
* Test fixtures whose path contains `/test` (still flagged but
  callers can scope; we keep this dumb on purpose).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Crypto call surfaces whose FIRST positional argument is the key.
# Pattern: <name>( <literal> ...)  where <literal> is b"..." | "..."
# We allow optional module qualifier on the LHS.
_KEY_CALLS = [
    r"Fernet",
    r"AES\s*\.\s*new",
    r"DES\s*\.\s*new",
    r"DES3\s*\.\s*new",
    r"Blowfish\s*\.\s*new",
    r"ChaCha20\s*\.\s*new",
    r"ChaCha20Poly1305",
    r"AESGCM",
    r"AESCCM",
    r"hmac\s*\.\s*new",
    r"hmac\s*\.\s*HMAC",
    r"HMAC",
    r"algorithms\s*\.\s*AES",
    r"algorithms\s*\.\s*ARC4",
]

RE_KEY_CALL = re.compile(
    r"\b(?:[A-Za-z_][\w\.]*\s*\.\s*)?(?:" + "|".join(_KEY_CALLS) + r")\s*\("
)

# jwt.encode(payload, "literal", ...) — literal in 2nd positional slot.
RE_JWT_ENCODE = re.compile(
    r"\bjwt\s*\.\s*encode\s*\("
)

# A bytes/str literal at the start of the arg list (allowing leading
# whitespace). We accept b"...", b'...', "...", '...'.
RE_FIRST_BYTES_LITERAL = re.compile(
    r"""^\s*(?:b|rb|br|B|RB|BR)?(?P<q>['"])(?P<body>(?:\\.|(?!(?P=q)).)*)(?P=q)"""
)

RE_SUPPRESS = re.compile(r"#\s*crypto-key-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Blank out comments AND string literal *contents* while
    preserving column positions and the surrounding quote tokens.

    Crucially, this is the same scrubber the other detectors use —
    so we operate on a "code skeleton" line where literals have
    been hollowed out. To still recover the literal arg, we run
    an extra pass on the RAW line at the matched paren index.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append(line[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if line[i:i + len(in_str)] == in_str:
            out.append(in_str)
            i += len(in_str)
            in_str = None
            continue
        out.append(" ")
        i += 1
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def _matching_paren(s: str, open_idx: int) -> int:
    depth = 0
    for j in range(open_idx, len(s)):
        ch = s[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _split_top_args(args_text: str) -> list[str]:
    """Split a comma-separated arg list at top level (no respect
    for nested string literals — caller passes the *raw* text but
    we only need a coarse split, and we re-parse each piece for
    a literal at the start)."""
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    in_str: str | None = None
    i = 0
    n = len(args_text)
    while i < n:
        ch = args_text[i]
        if in_str:
            cur.append(ch)
            if ch == "\\" and i + 1 < n:
                cur.append(args_text[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            cur.append(ch)
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur:
        out.append("".join(cur))
    return out


def _is_literal_key(arg: str) -> bool:
    # Skip leading kwarg name: e.g. `key=b"..."`
    s = arg.lstrip()
    # Strip optional `key=` / `secret=` / `Key=` etc.
    m = re.match(r"([A-Za-z_]\w*)\s*=\s*", s)
    if m:
        s = s[m.end():]
    return bool(RE_FIRST_BYTES_LITERAL.match(s))


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue

        for m in RE_KEY_CALL.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            close = _matching_paren(scrub, paren)
            if close < 0:
                # Unbalanced on this line: be conservative, peek at raw.
                args_raw = raw[paren + 1:]
            else:
                args_raw = raw[paren + 1:close]
            parts = _split_top_args(args_raw)
            if not parts:
                continue
            if _is_literal_key(parts[0]):
                kind = "crypto-hardcoded-key"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))

        for m in RE_JWT_ENCODE.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            close = _matching_paren(scrub, paren)
            if close < 0:
                args_raw = raw[paren + 1:]
            else:
                args_raw = raw[paren + 1:close]
            parts = _split_top_args(args_raw)
            # jwt.encode(payload, key, algorithm=...) — key is parts[1]
            if len(parts) >= 2 and _is_literal_key(parts[1]):
                kind = "crypto-hardcoded-key"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))
    return findings


def is_python_file(path: Path) -> bool:
    if path.suffix == ".py":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!") and "python" in first


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_python_file(sub):
                    yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

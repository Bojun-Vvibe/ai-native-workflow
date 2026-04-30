#!/usr/bin/env python3
"""Detect weak-hash usage (MD5, SHA1) in Python source.

LLMs asked to "hash this password" or "make a content fingerprint
for this token" routinely emit `hashlib.md5(...)` or
`hashlib.sha1(...)`. Both are broken for security contexts
(collision resistance, password storage, signature digests, HMAC
key derivation). This detector flags those calls so a human can
decide whether the use is non-security (e.g. cache-key bucketing,
where it carries an explicit allow-comment) or security-relevant
(in which case it must be rewritten to SHA-256/512, BLAKE2, or a
KDF such as bcrypt/argon2/scrypt/PBKDF2).

What this flags
---------------
* `hashlib.md5(...)`        and `hashlib.sha1(...)`
* `hashlib.new("md5", ...)` and `hashlib.new("sha1", ...)`
  (case-insensitive, dashes/underscores tolerated)
* `from hashlib import md5` / `from hashlib import sha1`
  followed by a bare `md5(...)` / `sha1(...)` call

What this does NOT flag
-----------------------
* `hashlib.sha256(...)`, `sha384`, `sha512`, `blake2b`, `blake2s`
* Lines marked with a trailing `# weak-hash-ok` comment
* Occurrences inside `#` comments or string / docstring literals

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_HASHLIB_DIRECT = re.compile(r"\bhashlib\s*\.\s*(md5|sha1)\s*\(")
RE_HASHLIB_NEW = re.compile(
    r"""\bhashlib\s*\.\s*new\s*\(\s*['"]\s*(md[-_]?5|sha[-_]?1)\s*['"]""",
    re.IGNORECASE,
)
RE_FROM_IMPORT = re.compile(
    r"""^\s*from\s+hashlib\s+import\s+([^\n#]+)"""
)
RE_BARE_CALL = re.compile(r"\b(md5|sha1)\s*\(")

RE_SUPPRESS = re.compile(r"#\s*weak-hash-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Mask out `#` comments and the *contents* of string literals
    (single + triple), preserving column positions. Triple-quote
    state is carried across lines."""
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


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    lines = text.splitlines()
    scrubbed: list[str] = []
    cursor: str | None = None
    for raw in lines:
        s, cursor = strip_comments_and_strings(raw, cursor)
        scrubbed.append(s)

    # Track which bare names were imported from hashlib.
    imported: set[str] = set()
    for raw, scrub in zip(lines, scrubbed):
        m = RE_FROM_IMPORT.match(scrub)
        if not m:
            continue
        names = m.group(1)
        # Strip parens if `from hashlib import (md5, sha1)`.
        names = names.replace("(", " ").replace(")", " ")
        for tok in names.split(","):
            tok = tok.strip().split()[0] if tok.strip() else ""
            # handle `md5 as hasher`
            tok = tok.split(" as ")[0].strip()
            if tok in {"md5", "sha1"}:
                imported.add(tok)

    for idx, scrub in enumerate(scrubbed):
        raw = lines[idx]
        if RE_SUPPRESS.search(raw):
            continue

        for m in RE_HASHLIB_DIRECT.finditer(scrub):
            algo = m.group(1).lower()
            findings.append(
                (path, idx + 1, m.start() + 1, f"weak-hash-{algo}", raw.strip())
            )

        # `hashlib.new("md5", ...)` keeps the algo name inside a
        # string literal; the scrubbed line has the literal blanked
        # out, so we anchor on `hashlib.new(` in `scrub` (to ensure
        # the call is not itself inside a literal/comment) and then
        # re-probe the corresponding `raw` line for the algo name.
        for m in re.finditer(r"\bhashlib\s*\.\s*new\s*\(", scrub):
            tail_raw = raw[m.end() - 1:]  # starts at "("
            mn = RE_HASHLIB_NEW.match("hashlib.new" + tail_raw)
            if mn:
                algo_token = mn.group(1).lower().replace("-", "").replace("_", "")
                findings.append(
                    (path, idx + 1, m.start() + 1, f"weak-hash-new-{algo_token}", raw.strip())
                )

        if imported:
            for m in RE_BARE_CALL.finditer(scrub):
                name = m.group(1)
                if name not in imported:
                    continue
                # Avoid double-counting `hashlib.md5(` matches above.
                start = m.start()
                preceding = scrub[max(0, start - 8):start]
                if preceding.rstrip().endswith("hashlib."):
                    continue
                # Skip when the bare token is part of an attribute
                # access like `obj.md5(` — only flag plain calls.
                if start > 0 and scrub[start - 1] == ".":
                    continue
                findings.append(
                    (path, idx + 1, start + 1, f"weak-hash-bare-{name}", raw.strip())
                )

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

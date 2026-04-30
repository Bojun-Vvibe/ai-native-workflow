#!/usr/bin/env python3
"""Detect hard-coded credentials in LLM-emitted Python source.

See README.md for full description, CWE references, and limitations.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# hardcoded-password-ok"

# Names that look like a credential. Word-boundary, case-insensitive.
CRED_NAMES = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "apikey",
    "api_token",
    "access_token",
    "auth_token",
    "bearer_token",
    "refresh_token",
    "private_key",
    "client_secret",
    "aws_secret_access_key",
    "db_password",
    "database_password",
    "postgres_password",
    "mysql_password",
    "redis_password",
)

# Names containing "key"/"secret" substrings that we explicitly do NOT
# treat as a credential. Public keys are public.
NON_CRED_NAMES = (
    "primary_key",
    "foreign_key",
    "sort_key",
    "cache_key",
    "partition_key",
    "public_key",
    "object_key",
    "row_key",
    "hash_key",
    "range_key",
    "shard_key",
    "lookup_key",
    "dict_key",
    "map_key",
    "key_name",
    "key_id",
    "key_type",
    "secret_name",
    "secret_id",
    "secret_arn",
)

# Build a single alternation. Longer names first so the regex prefers
# ``aws_secret_access_key`` over ``secret``.
_CRED_ALT = "|".join(sorted(CRED_NAMES, key=len, reverse=True))

# Match an assignment:    NAME = "literal"
# NAME may be qualified (self.password, cls._SECRET) or include a
# trailing comparator like dict literals handled separately below.
RE_ASSIGN = re.compile(
    rf"""
    (?P<lhs>
        (?:[A-Za-z_][\w.]*\s*\.\s*)?       # optional qualifier
        (?P<name>\b(?:{_CRED_ALT})\b)      # credential-looking name
    )
    \s*=\s*                                # assignment (NOT ==)
    (?!=)                                  # not part of ==
    (?P<rhs>
        (?:[rRbBuU]{{0,2}})                # optional non-f prefix
        (?P<q>'''|\"\"\"|'|\")             # opening quote
        (?P<val>(?:(?!(?P=q)).)*)          # body
        (?P=q)                             # closing quote
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Dict literal entry: "password": "hunter2"
RE_DICT_ENTRY = re.compile(
    rf"""
    (?P<keyq>'|\")
    (?P<keyname>\b(?:{_CRED_ALT})\b)
    (?P=keyq)
    \s*:\s*
    (?:[rRbBuU]{{0,2}})
    (?P<vq>'|\")
    (?P<val>(?:(?!(?P=vq)).)*)
    (?P=vq)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Keyword arg: password="hunter2"
RE_KWARG = re.compile(
    rf"""
    (?<![A-Za-z0-9_.])                     # name boundary
    (?P<kw>\b(?:{_CRED_ALT})\b)
    \s*=\s*
    (?:[rRbBuU]{{0,2}})
    (?P<q>'|\")
    (?P<val>(?:(?!(?P=q)).)*)
    (?P=q)
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _strip_comment(line: str) -> str:
    """Remove ``#`` comments while respecting string literals."""
    out: list[str] = []
    in_s = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < len(line):
                out.append(ch)
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                in_s = False
            out.append(ch)
        else:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_s = True
                quote = ch
            out.append(ch)
        i += 1
    return "".join(out)


def _is_non_cred(name: str) -> bool:
    n = name.lower()
    return any(n == bad or n.endswith("_" + bad) for bad in NON_CRED_NAMES)


def _value_is_meaningful(val: str) -> bool:
    """Reject empty / placeholder-ish literals."""
    if val == "":
        return False
    return True


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        line = _strip_comment(raw)

        # Reject lines that look like the RHS is a function call (env
        # lookup etc): NAME = something(...)
        m_assign = RE_ASSIGN.search(line)
        reported = False
        if m_assign:
            lhs_full = m_assign.group("lhs")
            name = m_assign.group("name")
            val = m_assign.group("val")
            if (
                not _is_non_cred(lhs_full)
                and _value_is_meaningful(val)
            ):
                findings.append(
                    (path, lineno, "hardcoded-password-assign", raw.rstrip())
                )
                reported = True

        if not reported:
            m_dict = RE_DICT_ENTRY.search(line)
            if m_dict and _value_is_meaningful(m_dict.group("val")):
                findings.append(
                    (path, lineno, "hardcoded-password-dict-entry", raw.rstrip())
                )
                reported = True

        if not reported:
            m_kw = RE_KWARG.search(line)
            if m_kw and _value_is_meaningful(m_kw.group("val")):
                # Avoid double-firing on plain assignments (already handled).
                # An assignment has form NAME = "..." at start-ish; a
                # kwarg appears inside parentheses.
                # Heuristic: there must be a "(" before the kwarg on the
                # same line for it to count as a call kwarg.
                kw_pos = m_kw.start()
                if "(" in line[:kw_pos]:
                    findings.append(
                        (path, lineno, "hardcoded-password-kwarg", raw.rstrip())
                    )
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

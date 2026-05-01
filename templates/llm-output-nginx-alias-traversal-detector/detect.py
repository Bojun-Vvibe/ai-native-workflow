#!/usr/bin/env python3
"""
llm-output-nginx-alias-traversal-detector

Flags nginx config blocks that combine a `location` prefix lacking a
trailing slash with an `alias` directive ending in a slash. This is
the canonical CWE-22 (path traversal) misconfiguration: a request
for `/static../etc/passwd` is rewritten to
`/var/www/static/../etc/passwd` and resolved upward, exposing
arbitrary files on the host filesystem.

LLMs reproduce this anti-pattern reliably when asked "serve static
files from nginx with alias": the model writes
`location /static { alias /var/www/static/; }` because most blog
snippets do, and the slash mismatch is invisible to the eye.

What this flags
---------------
A finding is emitted for any non-regex `location` block where:

* The location prefix does NOT end with `/` (and is not a regex
  modifier `~`, `~*`, `=`, or `^~ /something/`).
* The block body contains `alias <path>;` where `<path>` ends with
  `/`.

What this does NOT flag
-----------------------
* `location /static/ { alias /var/www/static/; }` — slashes match.
* `location /static { alias /var/www/static; }` — neither has a
  trailing slash.
* `location ~ ^/static/ { ... alias ... }` — regex locations are not
  affected by the slash-stripping behaviour that powers the bug.
* `root` directives — the bug is specific to `alias` (root has
  different concatenation semantics).
* Comments (lines starting with `#`).

Stdlib only. Reads files passed on argv (or recurses into directories,
matching `*.conf`, `nginx.conf`, and `*.conf.txt`).
Exit 0 = no findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# location <prefix> { ... }  — capture prefix + brace span.
# We only handle prefix locations (not regex / exact match): no leading
# `~`, `~*`, `=`, or `^~`.
_LOCATION_RE = re.compile(
    r"""(?xm)
    ^[ \t]*location[ \t]+
    (?P<prefix>(?!~|=|\^~)\S+)        # plain prefix path, not regex/exact
    [ \t]*\{
    """
)

# alias <path>;  — path may be quoted.
_ALIAS_RE = re.compile(
    r"""(?xm)
    ^[ \t]*alias[ \t]+
    (?P<path>(?:"[^"]*"|'[^']*'|[^;\s]+))
    [ \t]*;
    """
)


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _strip_comments(text: str) -> str:
    """Drop `# ...` comments (nginx uses # only) but preserve newlines
    so line numbers stay correct."""
    out = []
    for line in text.splitlines(keepends=True):
        # Find first `#` not inside a quoted string. nginx values rarely
        # use #, so a naive split is acceptable for the configs we scan.
        idx = line.find("#")
        if idx >= 0:
            # Preserve the trailing newline.
            tail = "\n" if line.endswith("\n") else ""
            out.append(line[:idx].rstrip(" \t") + tail)
        else:
            out.append(line)
    return "".join(out)


def _find_block_end(text: str, brace_open: int) -> int:
    """Given index of `{`, return index of matching `}`.
    Returns -1 if unbalanced."""
    depth = 0
    i = brace_open
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _line_no(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    cleaned = _strip_comments(text)

    for m in _LOCATION_RE.finditer(cleaned):
        prefix = m.group("prefix")
        # The bug only matters when prefix has no trailing slash.
        if prefix.endswith("/"):
            continue

        brace = cleaned.find("{", m.end() - 1)
        if brace < 0:
            continue
        end = _find_block_end(cleaned, brace)
        if end < 0:
            continue

        body = cleaned[brace + 1 : end]
        for am in _ALIAS_RE.finditer(body):
            alias_path = _strip_quotes(am.group("path"))
            if alias_path.endswith("/"):
                # Compute line in the original text. Since we preserved
                # newlines when stripping comments, offsets line up.
                alias_off = brace + 1 + am.start()
                findings.append(
                    f"{path}:{_line_no(cleaned, alias_off)}: nginx "
                    f"location '{prefix}' (no trailing slash) with alias "
                    f"'{alias_path}' (trailing slash) — CWE-22 path "
                    f"traversal: requests like '{prefix}../etc/passwd' "
                    f"escape the alias root"
                )

    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if (
                        f.endswith(".conf")
                        or f.endswith(".conf.txt")
                        or f == "nginx.conf"
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

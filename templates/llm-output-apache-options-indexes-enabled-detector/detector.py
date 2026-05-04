#!/usr/bin/env python3
"""Detect Apache HTTPD configurations whose ``Options`` directive
enables directory indexing.

Apache's ``mod_autoindex`` renders an HTML directory listing for any
URL that resolves to a filesystem directory with no matching
``DirectoryIndex`` entry, when the effective ``Options`` set
includes ``Indexes`` (or ``All``, which is a superset). That listing
exposes filenames the operator never intended to publish (``*.bak``,
``*.swp``, ``backup.sql.gz``, ``.git/`` artefacts, stale uploads),
producing a CWE-548 information-disclosure finding.

LLM-generated configs frequently emit shapes like::

    <Directory "/var/www/html">
        Options Indexes FollowSymLinks
    </Directory>

    <Directory /srv/uploads>
        Options +Indexes
    </Directory>

    <Directory /var/www>
        Options All
    </Directory>

What's checked, per file:
  - Every line whose first non-whitespace token (case-insensitive)
    is ``Options`` is parsed.
  - The directive's argument list is tokenized on whitespace and
    commas.
  - The file is flagged when any token is, case-insensitively:
      * ``Indexes``        (bare form, sets the option)
      * ``+Indexes``       (explicit additive form)
      * ``All``            (Apache: All == ExecCGI Includes
                            IncludesNOEXEC Indexes MultiViews
                            SymLinksIfOwnerMatch FollowSymLinks)
  - …UNLESS the same directive also contains ``-Indexes``
    anywhere in the token list (operator explicitly removed it).

Continuation lines (Apache supports trailing ``\\`` continuation)
are folded before tokenization. Comments (``#`` to end of line)
are stripped. Quoted arguments are honored.

Accepted (not flagged):
  - ``Options None``, ``Options FollowSymLinks``,
    ``Options ExecCGI``, ``Options -Indexes``, etc.
  - Files containing the comment ``# apache-indexes-allowed``.
  - Files with no ``Options`` directive.
  - Non-Apache files (selected by extension when scanning a
    directory: ``.conf``, ``.htaccess``).

Usage::

    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at
255). Stdout: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*apache-indexes-allowed", re.IGNORECASE)

OPTIONS_LINE_RE = re.compile(r"^\s*Options\b(?P<rest>.*)$", re.IGNORECASE)


def _strip_comment(line: str) -> str:
    # Apache treats `#` at the start of a token as a comment. To
    # avoid eating `#` that occurs inside a quoted argument, walk
    # the line manually.
    out = []
    in_str = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str = True
                quote = ch
                out.append(ch)
            elif ch == "#":
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _fold_continuations(source: str) -> List[Tuple[int, str]]:
    """Fold Apache trailing-backslash continuations.

    Returns list of (start_line_no, joined_line).
    """
    raw_lines = source.splitlines()
    result: List[Tuple[int, str]] = []
    buf = ""
    buf_line = 0
    for idx, line in enumerate(raw_lines, start=1):
        stripped = line.rstrip()
        if stripped.endswith("\\") and not stripped.endswith("\\\\"):
            if not buf:
                buf_line = idx
            buf += stripped[:-1] + " "
            continue
        if buf:
            result.append((buf_line, buf + line))
            buf = ""
            buf_line = 0
        else:
            result.append((idx, line))
    if buf:
        result.append((buf_line, buf))
    return result


def _tokenize_options_args(rest: str) -> List[str]:
    # Apache allows whitespace and commas. shlex handles quoting;
    # then we split each token on commas.
    try:
        coarse = shlex.split(rest, posix=True)
    except ValueError:
        coarse = rest.split()
    tokens: List[str] = []
    for t in coarse:
        for sub in t.split(","):
            sub = sub.strip()
            if sub:
                tokens.append(sub)
    return tokens


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    for line_no, raw in _fold_continuations(source):
        no_comment = _strip_comment(raw)
        m = OPTIONS_LINE_RE.match(no_comment)
        if not m:
            continue
        tokens = _tokenize_options_args(m.group("rest"))
        if not tokens:
            continue
        lowered = [t.lower() for t in tokens]
        # Explicit removal anywhere wins.
        if any(t == "-indexes" for t in lowered):
            continue
        enabling = None
        for t, lt in zip(tokens, lowered):
            if lt in {"indexes", "+indexes", "all"}:
                enabling = t
                break
        if enabling is None:
            continue
        findings.append(
            (
                line_no,
                f"Apache Options directive enables directory listing "
                f"via '{enabling}' (CWE-548)",
            )
        )
    return findings


def _is_apache_conf(path: Path) -> bool:
    name = path.name.lower()
    if name == ".htaccess":
        return True
    if name.endswith(".conf"):
        return True
    if name in {"httpd.conf", "apache2.conf"}:
        return True
    return False


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and _is_apache_conf(f):
                    targets.append(f)
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

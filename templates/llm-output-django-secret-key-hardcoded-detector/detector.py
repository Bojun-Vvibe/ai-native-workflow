#!/usr/bin/env python3
"""Detect Django ``settings.py``-style files that hardcode ``SECRET_KEY``
to a literal string instead of reading it from the environment, a
secrets manager, or a key-derivation step.

A hardcoded ``SECRET_KEY`` is a high-impact footgun: it signs session
cookies, password-reset tokens, ``signing.dumps`` payloads,
``PasswordResetTokenGenerator`` outputs, CSRF tokens (older Django),
and ``messages`` framework cookies. If the value is committed to a
repo, anyone with read access can forge any of those.

LLMs asked to "give me a Django settings.py" routinely produce::

    SECRET_KEY = "django-insecure-9!*8z@..."
    SECRET_KEY = 'changeme'
    SECRET_KEY = "abc123"

This detector flags those shapes in any ``*.py`` file (Django settings
files are not always named ``settings.py``).

What's flagged
--------------
* ``SECRET_KEY = "<literal>"`` / ``SECRET_KEY = '<literal>'``
* ``SECRET_KEY: str = "<literal>"`` (PEP-526 annotated assignment)
* f-strings whose contents are entirely a literal (no ``{...}``):
  ``SECRET_KEY = f"abc"``
* Concatenated string literals: ``SECRET_KEY = "abc" + "def"``
* ``SECRET_KEY`` set inside a class body or dict literal whose value
  is a bare string literal (e.g. config dicts shipped to Django).

What's NOT flagged
------------------
* ``SECRET_KEY = os.environ["X"]`` / ``os.environ.get("X")``
* ``SECRET_KEY = os.getenv("X", default)`` even when default is a
  string (treated as a fallback, not the canonical value).
* ``SECRET_KEY = config("X")`` / ``env("X")`` / ``Env()(...)`` style
  helpers from ``python-decouple``, ``django-environ``, etc.
* ``SECRET_KEY = SECRETS["X"]`` / ``vault.get("...")`` / any
  subscription or attribute access (non-literal RHS).
* Lines marked with a trailing ``# secret-key-ok`` comment, intended
  for test fixtures and ephemeral CI keys.
* Files containing ``# secret-key-ok-file`` at the top.

CWE refs
--------
* CWE-798: Use of Hard-coded Credentials
* CWE-321: Use of Hard-coded Cryptographic Key
* CWE-547: Use of Hard-coded, Security-relevant Constants

Usage
-----
    python3 detector.py <file_or_dir> [...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS_LINE = re.compile(r"#\s*secret-key-ok\b")
SUPPRESS_FILE = re.compile(r"#\s*secret-key-ok-file\b")

# Match `SECRET_KEY` assignment, optionally annotated, optionally
# inside a dict literal (`"SECRET_KEY":` form is handled separately).
ASSIGN_RE = re.compile(
    r"""^(?P<indent>\s*)
        (?:SECRET_KEY)
        (?:\s*:\s*[\w\[\], .]+)?      # optional type annotation
        \s*=\s*
        (?P<rhs>.+?)                   # right-hand side
        \s*(?:\#.*)?$                  # optional trailing comment
    """,
    re.VERBOSE,
)

DICT_KEY_RE = re.compile(
    r"""^(?P<indent>\s*)
        ['"]SECRET_KEY['"]
        \s*:\s*
        (?P<rhs>.+?)
        \s*,?\s*(?:\#.*)?$
    """,
    re.VERBOSE,
)

# A "string-literal expression" RHS: one or more string literals,
# possibly f-strings without `{...}`, joined by `+` only.
STRING_LITERAL_RE = re.compile(
    r"""(?:[fFrRbBuU]{0,2}             # optional string prefix
            (?:'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*")
        )"""
    ,
    re.VERBOSE,
)


def _rhs_is_pure_string_literal(rhs: str) -> bool:
    """True iff RHS is one or more string literals joined by `+`,
    with no interpolation (no ``{...}`` inside f-strings) and no
    other expression elements."""
    rhs = rhs.strip()
    if not rhs:
        return False
    # Walk literals and `+` separators only.
    pos = 0
    saw_literal = False
    while pos < len(rhs):
        m = STRING_LITERAL_RE.match(rhs, pos)
        if not m:
            return False
        literal = m.group(0)
        # Reject f-strings that contain `{` not doubled (i.e. real
        # interpolation). A doubled `{{` is a literal brace.
        prefix_end = 0
        while prefix_end < len(literal) and literal[prefix_end] in "fFrRbBuU":
            prefix_end += 1
        prefix = literal[:prefix_end].lower()
        body = literal[prefix_end + 1 : -1]  # strip surrounding quote
        if "f" in prefix:
            # Replace doubled braces, then check for any remaining `{`.
            stripped = body.replace("{{", "").replace("}}", "")
            if "{" in stripped:
                return False
        saw_literal = True
        pos = m.end()
        # Skip whitespace and a single `+` separator.
        while pos < len(rhs) and rhs[pos] in " \t":
            pos += 1
        if pos < len(rhs) and rhs[pos] == "+":
            pos += 1
            while pos < len(rhs) and rhs[pos] in " \t":
                pos += 1
        elif pos < len(rhs):
            return False
    return saw_literal


def _is_suspicious(rhs: str) -> bool:
    """RHS is a hardcoded literal we should flag."""
    return _rhs_is_pure_string_literal(rhs)


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS_FILE.search(source):
        return findings
    for i, raw in enumerate(source.splitlines(), start=1):
        if SUPPRESS_LINE.search(raw):
            continue
        # Skip lines that are entirely inside a comment.
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        m = ASSIGN_RE.match(raw)
        if m and _is_suspicious(m.group("rhs")):
            findings.append((
                i,
                "SECRET_KEY assigned to a hardcoded string literal",
            ))
            continue
        m = DICT_KEY_RE.match(raw)
        if m and _is_suspicious(m.group("rhs")):
            findings.append((
                i,
                "SECRET_KEY in dict-literal mapped to hardcoded string",
            ))
    return findings


def _iter_py_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for sub in sorted(path.rglob("*.py")):
        if sub.is_file():
            yield sub


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    for root in paths:
        for f in _iter_py_files(root):
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

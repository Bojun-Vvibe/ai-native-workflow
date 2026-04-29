#!/usr/bin/env python3
"""Detect SNOBOL4 dynamic-execution sinks: ``CODE()``, ``EVAL()``,
``APPLY()``, and ``LOAD()``.

Why this matters
----------------
SNOBOL4 is a string-processing language with a *very* sharp eval edge:
the built-in ``CODE`` function takes a string of SNOBOL4 source,
compiles it on the fly, and returns an object that, when assigned to a
label or branched to, becomes part of the running program's control
flow.  ``EVAL`` does the same thing for an expression.  If the string
came from upstream input you have the same blast radius as
``eval($USER_INPUT)`` in any other language — and SNOBOL4 implementations
(SPITBOL, CSNOBOL4) routinely ship with ``HOST()`` / ``SYSTEM()`` for
shell access, so the attacker reaches out of the interpreter trivially.

Sinks flagged here
------------------
* ``CODE(s)``    — compile string ``s`` as a chunk of SNOBOL4 source;
                   the returned object is normally assigned to a label
                   variable and immediately branched to.  The textbook
                   SNOBOL4 self-modifying-code primitive.
* ``EVAL(s)``    — evaluate an expression string at run time.
* ``APPLY(s,..)`` — call a function whose name is given as a string.
                    SPITBOL/CSNOBOL4 extension; flagged because the
                    dispatched function is data-driven.
* ``LOAD(s)``    — load an external function from a shared library
                   named in ``s``.  Same blast radius as ``dlopen`` in C.

Out of scope (deliberately)
---------------------------
* ``DEFINE()`` over a *literal* prototype string — the standard way to
  define functions in SNOBOL4; the prototype is normally a literal in
  source.  We do not flag it.  (A reviewer who builds a prototype from
  upstream input is in trouble, but that is a separate, much rarer
  pattern.)
* ``HOST()``, ``SYSTEM()`` — direct shell-out hazards in their own
  right, but not text-resolver sinks.  A separate detector covers them.
* ``DATA()`` — declares a record type from a prototype; not a code
  sink even though the prototype is a string.

Suppression
-----------
A trailing ``* CODE-OK`` (or ``*CODE-OK``) on the same line
suppresses that line.  SNOBOL4 line comments are introduced by ``*``
in column 1, but the suppression marker may appear anywhere the
compiler would treat it as a comment fragment — we accept it as long
as it is preceded by an asterisk somewhere on the line.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise.  python3 stdlib only.
Recurses into directories looking for ``*.sno``, ``*.snobol``,
``*.spt`` (SPITBOL), ``*.sbl``, and files whose first line is a
SNOBOL4-ish shebang (``snobol4``, ``spitbol``, ``csnobol4``).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Sink as a function-call: NAME followed by `(`.  SNOBOL4 identifiers
# are uppercase letters, digits, `.`, and `_`; we additionally accept
# lowercase because some implementations (CSNOBOL4) are case-insensitive
# and LLM-emitted SNOBOL routinely mixes case.
RE_SINK = re.compile(
    r"(?<![A-Za-z0-9_\.])"
    r"(CODE|EVAL|APPLY|LOAD|code|eval|apply|load)"
    r"\s*\("
)

# Suppression marker.  SNOBOL4 line comments start with `*` in col 1;
# we accept the suppressor anywhere on the line as long as it is
# preceded by `*`.
RE_SUPPRESS = re.compile(r"\*+\s*CODE-OK\b", re.IGNORECASE)

# SNOBOL4 line-comment sniff: `*` in column 1.
def is_comment_line(s: str) -> bool:
    return s.startswith("*")


_SNO_EXTS = {".sno", ".snobol", ".spt", ".sbl"}
_SNO_SHEBANG_TOKENS = ("snobol4", "spitbol", "csnobol4")


def is_snobol_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _SNO_EXTS:
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if first.startswith("#!"):
        if any(tok in first.lower() for tok in _SNO_SHEBANG_TOKENS):
            return True
    return False


def strip_strings(line: str) -> str:
    """Blank out SNOBOL4 string-literal contents, preserving columns.

    SNOBOL4 has two string-literal forms:

    * ``'...'`` — single-quoted, no escapes (a doubled ``''`` is one
                  apostrophe in the literal)
    * ``"..."`` — double-quoted, no escapes (doubled ``""`` is one
                  quote in the literal)

    There are no backslash escapes.  Block comments do not exist —
    only the `*`-in-column-1 line comment.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch in ("'", '"'):
            quote = ch
            j = i + 1
            out.append(quote)
            while j < n:
                if line[j] == quote:
                    # Doubled-quote escape inside the string?
                    if j + 1 < n and line[j + 1] == quote:
                        out.append("  ")
                        j += 2
                        continue
                    out.append(quote)
                    j += 1
                    break
                out.append(" ")
                j += 1
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if is_comment_line(raw):
            continue
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_strings(raw)
        for m in RE_SINK.finditer(scrub):
            kind = "snobol-" + m.group(1).lower()
            findings.append((path, idx, m.start(1) + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_snobol_file(sub):
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

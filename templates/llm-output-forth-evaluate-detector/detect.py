#!/usr/bin/env python3
"""Detect Forth `EVALUATE` (and friends) on dynamic strings.

Forth's standard word ``EVALUATE ( c-addr u -- )`` takes a counted
string from the data stack and re-enters the text interpreter on it.
That is, whatever bytes happen to live at ``c-addr`` for ``u`` chars
become Forth source code at run time.  This is the same blast radius
as ``eval($USER_INPUT)`` in any other language.

Sibling words with the same hazard:

* ``EVALUATE``                     — ANS-Forth core, the canonical sink
* ``INTERPRET``                    — older / Gforth name for the inner
                                     text interpreter; calling it
                                     directly on a user buffer is the
                                     same hazard
* ``INCLUDED ( c-addr u -- )``     — load+evaluate the file whose name
                                     is given by the string on the
                                     stack; if the name is dynamic this
                                     is "load whatever the attacker
                                     points us at"
* ``INCLUDE``                      — parsing-word form; flagged when
                                     followed by a non-literal target
                                     (i.e. ``S" ... " INCLUDED`` style
                                     reachable via stack manipulation)

LLM-emitted Forth sometimes reaches for ``EVALUATE`` to "splice a
word that lives in a string buffer".  That is almost always wrong;
the safe forms are:

* compile the word once with ``: name ... ;`` and just execute it,
* keep an XT (execution token) and ``EXECUTE`` that, never re-parse,
* if you really must, isolate the call inside an audited word and
  add a ``\\ evaluate-ok`` suppression marker on that line.

What this flags
---------------
Bareword token (case-insensitive) ``EVALUATE``, ``INTERPRET``, or
``INCLUDED`` anywhere in the un-commented, un-stringified source.
Forth is whitespace-delimited, so a bareword check is exact.

* ``S" 2 2 + ." EVALUATE``                — UNSAFE, dynamic re-parse
* ``buf @ count EVALUATE``                — UNSAFE
* ``user-input dup strlen EVALUATE``      — UNSAFE
* ``S" plugins/foo.fs" INCLUDED``         — flagged (path is data; an
                                             LLM that builds this path
                                             from user input loads
                                             arbitrary code)
* ``: shell ... INTERPRET ;``             — flagged

Out of scope (deliberately)
---------------------------
* ``EXECUTE`` of a compile-time-bound XT — that is the safe pattern,
  not the sink we are looking for.
* ``POSTPONE``, ``[COMPILE]`` — compile-time word-splicing, different
  hazard, different detector.
* ``SYSTEM``/``SH`` (Gforth shell-out) — out of scope; this detector
  is Forth-text-interpreter only.

Suppression
-----------
A trailing ``\\ evaluate-ok`` (or ``( evaluate-ok )``) on the same
line suppresses that line.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise.  python3 stdlib only.
Recurses into directories looking for ``*.fs``, ``*.fth``, ``*.4th``,
``*.forth``, ``*.f`` (when the file does not look like a Fortran
fixed-form deck), and files whose first line is a Forth-ish shebang
(``gforth``, ``pforth``, ``vfx``).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Bareword token, case-insensitive.  Forth is whitespace-delimited so
# we anchor on whitespace / start / end.
RE_SINK = re.compile(
    r"(?:^|(?<=\s))(EVALUATE|INTERPRET|INCLUDED)(?=\s|$)",
    re.IGNORECASE,
)

# Suppression marker: `\ evaluate-ok` or `( evaluate-ok )` on the line.
RE_SUPPRESS = re.compile(r"(?:\\|\()\s*evaluate-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out Forth comment + string contents, preserving columns.

    Forth comment / string forms handled here:

    * ``\\ ... EOL``         — line comment, must be followed by ws or EOL
    * ``( ... )``            — paren comment, ws-delimited open paren
    * ``S" ... "``           — counted-string literal
    * ``." ... "``           — type-string literal
    * ``C" ... "``           — counted-string literal (ANS)
    * ``ABORT" ... "``       — message string

    Anything inside those is replaced with spaces so column offsets
    stay stable and so ``EVALUATE`` mentioned inside a comment or
    string literal is never flagged.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        # Line comment: backslash followed by whitespace or EOL.
        if ch == "\\" and (i + 1 == n or line[i + 1].isspace()):
            out.append(" " * (n - i))
            break
        # Paren comment: `(` must be ws-delimited (Forth word boundary).
        if ch == "(" and (i == 0 or line[i - 1].isspace()) and (
            i + 1 == n or line[i + 1].isspace()
        ):
            j = line.find(")", i + 1)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i + 1))
            i = j + 1
            continue
        # String-opening words: S" ." C" ABORT"
        # Each is a ws-delimited word ending in `"`, followed by a
        # space, followed by content, terminated by `"`.
        opener_match = None
        for opener in ('S"', '."', 'C"', 'ABORT"'):
            ln = len(opener)
            if line[i : i + ln].upper() == opener and (
                i == 0 or line[i - 1].isspace()
            ) and i + ln < n and line[i + ln] == " ":
                opener_match = (opener, ln)
                break
        if opener_match is not None:
            opener, ln = opener_match
            # Keep the opener word visible so it doesn't accidentally
            # become a bareword EVALUATE; replace contents with spaces.
            out.append(line[i : i + ln + 1])  # opener + the space
            j = line.find('"', i + ln + 1)
            if j == -1:
                # Unterminated; blank rest of line.
                out.append(" " * (n - (i + ln + 1)))
                break
            out.append(" " * (j - (i + ln + 1)))
            out.append('"')
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_FORTH_EXTS = {".fs", ".fth", ".4th", ".forth"}
_FORTH_SHEBANG_TOKENS = ("gforth", "pforth", "vfx", "swiftforth")


def is_forth_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _FORTH_EXTS:
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if first.startswith("#!"):
        if any(tok in first for tok in _FORTH_SHEBANG_TOKENS):
            return True
    # `.f` is ambiguous (Fortran vs Forth).  Treat as Forth only if a
    # Forth shebang is present.  We deliberately do NOT auto-claim `.f`.
    return False


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)
        for m in RE_SINK.finditer(scrub):
            kind = "forth-" + m.group(1).lower()
            findings.append((path, idx, m.start(1) + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_forth_file(sub):
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

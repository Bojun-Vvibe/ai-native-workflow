#!/usr/bin/env python3
"""Detect PostScript dynamic-execution sinks: ``exec``, ``cvx``, ``run``,
``token``, and ``loadfile``-style re-entry.

Why this matters
----------------
PostScript is a stack-based, homoiconic language: a *procedure* is just
an array of objects with the executable bit set.  Anything reachable
through ``exec`` is interpreted as code at run time.  If the array, the
string fed to ``cvx`` (convert-to-executable), or the file path passed
to ``run`` came from an upstream document, you have the same blast
radius as ``eval($USER_INPUT)`` in any other language — and the
interpreter has direct access to the host file system (``file``,
``deletefile``, ``renamefile``) and to other processes via the
``%pipe%`` device on most implementations.

Sinks flagged here
------------------
* ``exec``     — pop the operand and execute it as code.  The classic
                 sink: ``(stuff) cvx exec`` or ``mystring cvx exec``.
* ``cvx``      — convert-to-executable; flips the executable bit.  The
                 immediate predecessor of an ``exec``.  Flagged on its
                 own because LLM-emitted PostScript routinely splits the
                 two operations across lines.
* ``run``      — read a named file and execute its contents as
                 PostScript.  Equivalent to ``source $UNTRUSTED_PATH``
                 in shell.
* ``token``    — scan one PostScript token from a string and return it
                 as an executable object.  Paired with ``exec`` it is a
                 streaming eval.
* ``filenameforall`` — enumerate paths matching a pattern and apply a
                       procedure to each; the procedure is executed.
                       Flagged because the procedure body is often
                       built from the matched filename.

Out of scope (deliberately)
---------------------------
* ``def``, ``bind``, ``forall``, ``loop`` — control flow over literal
  procedures defined in source.  Not a string-eval sink.
* ``deletefile``, ``renamefile``, ``%pipe%`` — host-side hazards in
  their own right, but not text-resolver sinks.  A separate detector
  should cover those.
* DSC ``%%`` comment directives.

Suppression
-----------
A trailing ``% exec-ok`` (or ``%%exec-ok``) on the same line
suppresses that line.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise.  python3 stdlib only.
Recurses into directories looking for ``*.ps``, ``*.eps``, ``*.pdf``
(PDFs embed PostScript fragments via the ``Action`` and ``OpenAction``
dictionaries; flagged when the file starts with ``%!PS`` only — full
PDF parsing is out of scope), and files whose first line is the
PostScript magic ``%!PS``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Sink word as a standalone PostScript token.  PostScript tokens are
# whitespace-delimited; a word boundary in regex terms means
# non-`[A-Za-z0-9_]`, which is close enough — PostScript names may
# contain `-`, `.`, `?`, `!`, etc., but the sinks themselves do not,
# and a sink like ``exec`` never appears as a *substring* of a
# user-defined name without one of those separator characters next to
# it.  We additionally require a non-name character on each side.
RE_SINK = re.compile(
    r"(?<![A-Za-z0-9_\-\.\?\!])"
    r"(exec|cvx|run|token|filenameforall)"
    r"(?![A-Za-z0-9_\-\.\?\!])"
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"%+\s*exec-ok\b")

_PS_EXTS = {".ps", ".eps"}
_PS_MAGIC = "%!PS"


def strip_comments_and_strings(line: str) -> str:
    """Blank out PostScript comment + string contents, preserving
    columns.

    Forms handled:

    * ``% ... EOL``                — line comment (and DSC ``%%`` lines)
    * ``(...)``                    — parenthesised string literal,
                                     supports nested parens and the
                                     standard backslash escapes
    * ``<...>``                    — hex-string literal; contents are
                                     hex digits and whitespace, no
                                     sink words possible, but blank
                                     them anyway for symmetry
    * ``<<`` and ``>>``            — dict delimiters; left intact

    PostScript ``ASCII85`` strings (``<~ ... ~>``) are also blanked.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "%":
            out.append(" " * (n - i))
            break
        if ch == "(":
            depth = 1
            out.append("(")
            j = i + 1
            while j < n and depth > 0:
                c = line[j]
                if c == "\\" and j + 1 < n:
                    out.append("  ")
                    j += 2
                    continue
                if c == "(":
                    depth += 1
                    out.append(" ")
                    j += 1
                    continue
                if c == ")":
                    depth -= 1
                    if depth == 0:
                        out.append(")")
                        j += 1
                        break
                    out.append(" ")
                    j += 1
                    continue
                out.append(" ")
                j += 1
            i = j
            continue
        if ch == "<":
            # Dict delimiter `<<`?  Leave intact.
            if i + 1 < n and line[i + 1] == "<":
                out.append("<<")
                i += 2
                continue
            # ASCII85 `<~ ... ~>`?
            if i + 1 < n and line[i + 1] == "~":
                j = line.find("~>", i + 2)
                if j == -1:
                    out.append(" " * (n - i))
                    break
                out.append("<~")
                out.append(" " * (j - (i + 2)))
                out.append("~>")
                i = j + 2
                continue
            # Hex string `<...>`.
            j = line.find(">", i + 1)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append("<")
            out.append(" " * (j - i - 1))
            out.append(">")
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def is_postscript_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _PS_EXTS:
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith(_PS_MAGIC)


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
            kind = "postscript-" + m.group(1)
            findings.append((path, idx, m.start(1) + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_postscript_file(sub):
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

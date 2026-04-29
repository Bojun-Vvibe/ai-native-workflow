#!/usr/bin/env python3
"""Detect KornShell (ksh / ksh93) dynamic-code execution sinks.

ksh has multiple ways to take a string and run it as code, all of
which are code-injection sinks when the string contains attacker- or
LLM-controlled data:

  * eval ARGS                 -- joins ARGS with spaces and re-parses
                                 the result as shell input.
  * . FILE / source FILE      -- read and execute FILE in the current
                                 shell. With a non-literal path this
                                 is arbitrary code by another name.
  * command eval ARGS         -- bypass aliases/functions but still
                                 ``eval``.
  * (( EXPR ))                -- arithmetic eval; with a string built
                                 from input, ksh93 supports
                                 ``$(( var ))`` indirection that
                                 re-parses ``var`` as an expression.
  * ${FOO?...} / ${!FOO}      -- name-reference expansion; the ``!``
                                 form turns ``$FOO`` into a variable
                                 *name* lookup, executing whatever
                                 the controlled string names.

What this flags
---------------
A bareword call to ``eval`` , ``command eval`` , ``.`` (dot
include), ``source`` , or any indirect-name expansion ``${!NAME}`` /
``${!NAME[*]}`` / ``${!NAME[@]}``.

The detector is single-pass with comment + string-literal masking
so that occurrences inside ``# ...`` comments and inside ``'...'``
or ``"..."`` strings do not flag.

Suppression
-----------
A trailing ``# eval-ok`` comment on the same line suppresses the
finding on that line.

Out of scope
------------
* ``trap '...' SIGNAL`` -- the trap body is also re-parsed as shell
  but that is a separate detector.
* ``$(...)`` and backticks -- those are command substitution, not
  dynamic re-parsing of attacker data per se.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for ``*.ksh`` and files whose
first line is a ksh shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# ``eval`` as a command word: line start, ``;``, ``&&``, ``||``,
# ``|``, ``&``, ``(``, or ``{`` immediately before (modulo
# whitespace), then the literal ``eval`` followed by space/tab/EOL.
_CMD_PREFIX = r"(?:^|(?<=[;&|(){}]))[ \t]*"
RE_EVAL = re.compile(_CMD_PREFIX + r"(eval)(?=[ \t]|$)")
# ``command eval`` -- same shape, two words.
RE_COMMAND_EVAL = re.compile(
    _CMD_PREFIX + r"command[ \t]+(eval)(?=[ \t]|$)"
)
# ``builtin eval`` / ``exec eval`` -- ksh-specific wrappers.
RE_BUILTIN_EVAL = re.compile(
    _CMD_PREFIX + r"(?:builtin|exec)[ \t]+(eval)(?=[ \t]|$)"
)
# ``. FILE`` -- POSIX dot include. Must be a standalone ``.`` token,
# not part of ``./foo`` (relative path execution) or ``..``.
RE_DOT_INCLUDE = re.compile(
    _CMD_PREFIX + r"(\.)(?=[ \t]+\S)"
)
# ``source FILE`` -- ksh/bash spelling.
RE_SOURCE = re.compile(
    _CMD_PREFIX + r"(source)(?=[ \t]+\S)"
)
# Indirect name-reference expansion: ``${!FOO}`` , ``${!FOO[*]}``,
# ``${!FOO[@]}``. The ``!`` makes ksh look up the *name* stored in
# FOO and dereference that, which is the same hazard as eval over a
# variable name.
RE_INDIRECT = re.compile(r"\$\{(![A-Za-z_][A-Za-z0-9_]*)")

RE_SUPPRESS = re.compile(r"#\s*eval-ok\b")


def strip_comments_and_strings(line: str, state: dict) -> str:
    """Mask ``#`` comments and ``'...'`` / ``"..."`` strings.

    ksh single-quoted strings are literal (no escape processing,
    no ``$`` expansion). Double-quoted strings allow ``\\`` escapes
    and ``$``-expansion but for our purposes we mask their
    contents wholesale so eval-shaped substrings inside don't
    flag. ``state`` carries cross-line context for here-documents:

      ``hd`` : None | "TAG"   (inside an unquoted heredoc body
                                terminated by line == TAG)

    Heredoc content is masked. Heredoc *introducer* line is left
    visible so any ``eval`` etc. before the ``<<TAG`` still flags.
    """
    if state.get("hd") is not None:
        tag = state["hd"]
        if line.strip() == tag:
            state["hd"] = None
            return " " * len(line)
        return " " * len(line)

    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None
    while i < n:
        ch = line[i]
        if in_s is None:
            if ch == "#":
                # Only a comment if at start-of-token (preceded by
                # whitespace, line start, or shell op). This avoids
                # masking ``${#var}`` or ``$#``.
                if i == 0 or line[i - 1] in " \t;|&()":
                    out.append(" " * (n - i))
                    break
                out.append(ch)
                i += 1
                continue
            if ch == "'" or ch == '"':
                in_s = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside string
        if in_s == '"' and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == in_s:
            out.append(ch)
            in_s = None
            i += 1
            continue
        out.append(" ")
        i += 1

    # Detect heredoc introducer ``<<TAG`` or ``<<-TAG`` (NOT
    # ``<<<`` here-string). Quoted tag (``<<'TAG'``) still masks
    # the body the same way.
    masked = "".join(out)
    m = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*$",
                  masked)
    if m:
        state["hd"] = m.group(1)
    return masked


def is_ksh_file(path: Path) -> bool:
    if path.suffix in (".ksh", ".ksh93"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "ksh" in first


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    state: dict = {"hd": None}
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            strip_comments_and_strings(raw, state)
            continue
        scrub = strip_comments_and_strings(raw, state)
        seen_cols: set[int] = set()

        def emit(col: int) -> None:
            if col in seen_cols:
                return
            seen_cols.add(col)
            findings.append(
                (path, idx, col, "ksh-eval", raw.strip())
            )

        for m in RE_EVAL.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_COMMAND_EVAL.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_BUILTIN_EVAL.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_DOT_INCLUDE.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_SOURCE.finditer(scrub):
            emit(m.start(1) + 1)
        for m in RE_INDIRECT.finditer(scrub):
            emit(m.start(1) + 1)
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_ksh_file(sub):
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

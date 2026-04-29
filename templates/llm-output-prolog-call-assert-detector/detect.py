#!/usr/bin/env python3
"""Detect Prolog dynamic-goal sinks: ``call/N``, ``assert``/``assertz``/
``asserta``, ``term_to_atom`` round-trips that feed ``call``, and
``read_term_from_atom``-style re-entry.

Why this matters
----------------
In Prolog, a *goal* is just a term.  Any term reachable through
``call/N`` is interpreted as a goal at run time.  If the term came
from a string, an atom built from user input, or a fact asserted at
run time, you have the same blast radius as ``eval($USER_INPUT)`` in
any other language.  And because Prolog's resolution machinery is
turing-complete, the attacker doesn't even need the host shell to
get arbitrary control over the program.

Sinks flagged here
------------------
* ``call/1 .. call/8``     — the canonical "interpret this term as a
                              goal" sink.  ``call(Goal)``,
                              ``call(F, X)``, ``call(F, X, Y)``, etc.
* ``assert/1``,
  ``asserta/1``,
  ``assertz/1``             — install a clause into the database at
                              run time.  If the clause head/body came
                              from user input, every later predicate
                              call against that name is now untrusted.
* ``retract/1``,
  ``retractall/1``          — same database, same trust problem in
                              reverse: a user-controlled functor can
                              wipe rules out from under the program.
* ``term_to_atom/2``        — the standard atom↔term parser; LLM-emitted
                              code typically calls ``term_to_atom(T,
                              UserAtom), call(T)`` which is the
                              textbook Prolog injection sink.
* ``read_term_from_atom/3`` — same hazard, explicit atom-to-term
                              re-parse.

LLM-emitted Prolog reaches for ``call`` to "execute a predicate whose
name lives in a variable".  That is almost always wrong; the safe
forms are:

* keep a closed allowlist of goal terms, switch on it explicitly,
* use higher-order combinators on a fixed set of compiled predicates
  (``maplist/2``, ``foldl/4``) where the predicate symbol is a
  literal in source,
* never feed an atom built from user input into ``call`` or
  ``assert``.

Out of scope (deliberately)
---------------------------
* ``meta_predicate`` declarations — declarative metadata, not a sink.
* ``=..``  (univ) — term construction, dangerous *in combination* with
  ``call``, but ``call`` is the actual sink and is what we flag.
* ``apply/2`` (deprecated SWI-Prolog) — same hazard as ``call``; we
  flag it.
* SWI-specific shell-out (``shell/1``, ``process_create/3``) — out of
  scope for this Prolog-text-resolver detector.

Suppression
-----------
A trailing ``% call-ok`` (or ``%%call-ok``) on the same line
suppresses that line.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise.  python3 stdlib only.
Recurses into directories looking for ``*.pl``, ``*.pro``, ``*.prolog``,
``*.P``, and files whose first line is a Prolog-ish shebang
(``swipl``, ``gprolog``, ``yap``).

NOTE: ``.pl`` is heavily ambiguous (Perl).  We require that the file
either has a Prolog shebang, has an unambiguous extension, OR contains
a Prolog directive (``:- ...``) within the first 40 lines.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Sink word at the start of a functor application: WORD followed by
# `(`.  Word boundaries on both sides so `mycall(X)` is not flagged.
RE_SINK = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(call|apply|assert|asserta|assertz|retract|retractall|"
    r"term_to_atom|read_term_from_atom)"
    r"\s*\("
)

# Suppression marker: `% call-ok` anywhere on the line.
RE_SUPPRESS = re.compile(r"%+\s*call-ok\b")

# Prolog directive sniff: a line starting with `:-` (after optional
# whitespace) is a strong Prolog signal.
RE_DIRECTIVE = re.compile(r"^\s*:-")


def strip_comments_and_strings(line: str) -> str:
    """Blank out Prolog comment + string contents, preserving columns.

    Forms handled:

    * ``% ... EOL``               — line comment
    * ``"..."``                    — double-quoted string (codes/chars
                                     depending on flag; either way,
                                     contents are not goal source)
    * ``'...'``                    — single-quoted atom; the *contents*
                                     of a quoted atom are not Prolog
                                     source either, so blank them
                                     (``'\\''`` escape handled)
    * ``0'C``                       — character code literal; we leave
                                     it alone, it cannot contain a
                                     sink word

    We do NOT handle nested ``/* ... */`` block comments specially
    here because they can span lines; the file-level scanner handles
    block-comment state across lines.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "%":
            out.append(" " * (n - i))
            break
        if ch == '"':
            j = i + 1
            out.append('"')
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    out.append("  ")
                    j += 2
                    continue
                if line[j] == '"':
                    out.append('"')
                    j += 1
                    break
                out.append(" ")
                j += 1
            i = j
            continue
        if ch == "'":
            # `0'C` char-code literal: leave as-is.
            if i >= 1 and line[i - 1] == "0" and (
                i == 1 or not line[i - 2].isalnum()
            ):
                out.append(ch)
                i += 1
                continue
            j = i + 1
            out.append("'")
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    out.append("  ")
                    j += 2
                    continue
                if line[j] == "'":
                    # Escaped '' inside quoted atom?  In Prolog,
                    # doubled '' inside a quoted atom is one quote.
                    if j + 1 < n and line[j + 1] == "'":
                        out.append("  ")
                        j += 2
                        continue
                    out.append("'")
                    j += 1
                    break
                out.append(" ")
                j += 1
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_block_comments(text: str) -> str:
    """Replace ``/* ... */`` regions with spaces (preserving newlines
    and column positions).  Block comments may span lines."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                # Unterminated; blank to end, preserving newlines.
                for ch in text[i:]:
                    out.append("\n" if ch == "\n" else " ")
                break
            for ch in text[i : j + 2]:
                out.append("\n" if ch == "\n" else " ")
            i = j + 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


_PROLOG_EXTS_STRONG = {".pro", ".prolog", ".P"}
_PROLOG_AMBIGUOUS_EXTS = {".pl"}
_PROLOG_SHEBANG_TOKENS = ("swipl", "gprolog", "yap", "sicstus")


def is_prolog_file(path: Path) -> bool:
    suffix = path.suffix
    if suffix in _PROLOG_EXTS_STRONG:
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = [next(fh, "") for _ in range(40)]
    except OSError:
        return False
    if head and head[0].startswith("#!"):
        if any(tok in head[0] for tok in _PROLOG_SHEBANG_TOKENS):
            return True
        # Shebang for something else — not Prolog.
        if suffix in _PROLOG_AMBIGUOUS_EXTS:
            return False
    if suffix in _PROLOG_AMBIGUOUS_EXTS:
        # Sniff for a Prolog directive within the first 40 lines.
        for ln in head:
            if RE_DIRECTIVE.match(ln):
                return True
        return False
    return False


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    text = strip_block_comments(text)
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)
        for m in RE_SINK.finditer(scrub):
            kind = "prolog-" + m.group(1).replace("_", "-")
            findings.append((path, idx, m.start(1) + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_prolog_file(sub):
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

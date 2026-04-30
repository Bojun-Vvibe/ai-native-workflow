#!/usr/bin/env python3
"""Detect ``shell=True`` usage in ``subprocess`` calls in LLM-emitted Python.

When ``subprocess.run`` / ``Popen`` / ``call`` / ``check_call`` /
``check_output`` are invoked with ``shell=True`` and the command argument
is a string built from any non-literal source (variable, f-string,
``%`` formatting, ``.format``, concatenation), the shell metacharacters
in the interpolated value are interpreted by ``/bin/sh``. A user input
of ``"; rm -rf ~"`` then becomes a command separator, not a literal.

LLMs reach for ``shell=True`` by reflex because:

1. It lets the model emit a single string ("ls -la /tmp") instead of
   reasoning about argv tokenisation.
2. Pipes / redirection (``|``, ``>``) only work via the shell, so the
   model assumes "shell=True is needed for pipes".
3. Pre-2018 Stack Overflow answers default to ``shell=True``.

CWE references
--------------
* **CWE-78**:  OS Command Injection.
* **CWE-77**:  Improper Neutralization of Special Elements used in a Command.
* **CWE-88**:  Argument Injection.

What this flags
---------------
* Any ``subprocess.<run|Popen|call|check_call|check_output>(...,
  shell=True, ...)`` where the first positional argument is NOT a bare
  string literal — i.e. it is a variable name, f-string, ``%`` /
  ``.format`` expression, or string concatenation.
* ``os.system(<expr>)`` where ``<expr>`` is not a bare string literal.
* ``os.popen(<expr>)`` with the same condition.
* ``commands.getoutput(<expr>)`` / ``commands.getstatusoutput(<expr>)``
  (Python 2 holdover that LLMs still emit).

What this does NOT flag
-----------------------
* ``subprocess.run(["ls", "-la", path])`` — argv form, no shell.
* ``subprocess.run("ls -la", shell=True)`` — fully literal command,
  no interpolation, low risk (still noisy but not injection).
* ``os.system("date")`` — fully literal.
* Lines suffixed with the suppression marker ``# shell-true-ok``
  (e.g. tightly controlled command construction with ``shlex.quote``
  on every interpolated arg, audited).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# shell-true-ok"

RE_SHELL_TRUE = re.compile(r"\bshell\s*=\s*True\b")

# subprocess.<func>(  capturing the function name and rest of line.
RE_SUBPROCESS_CALL = re.compile(
    r"\bsubprocess\s*\.\s*(run|Popen|call|check_call|check_output)\s*\("
)

# os.system( / os.popen(
RE_OS_SYSTEM = re.compile(r"\bos\s*\.\s*system\s*\(")
RE_OS_POPEN = re.compile(r"\bos\s*\.\s*popen\s*\(")

# commands.getoutput( / getstatusoutput(  (Py2 compat shim, still emitted)
RE_COMMANDS_GET = re.compile(r"\bcommands\s*\.\s*get(?:status)?output\s*\(")

# Bare string literal: optional whitespace, then a single string literal,
# then a closing paren or comma. We accept r/b/u/f prefixes — but f-strings
# are interpolation and must NOT be considered "bare".
RE_BARE_LITERAL_ARG = re.compile(
    r"""
    \(\s*                       # opening paren of the call
    (?:[rRbBuU]{1,2})?          # optional non-f prefix
    (?P<q>'''|\"\"\"|'|\")      # opening quote
    (?:                         # body: no backslash, no quote, no { for safety
        (?!(?P=q)).
    )*?
    (?P=q)                      # closing quote (same kind)
    \s*[,)]                     # then a comma or the closing paren
    """,
    re.VERBOSE,
)


def _strip_comment_and_strings(line: str) -> str:
    """Replace string-literal contents with spaces, drop ``#`` comments."""
    out: list[str] = []
    in_s = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < len(line):
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                in_s = False
                out.append(ch)
            else:
                out.append(" ")
        else:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_s = True
                quote = ch
                out.append(ch)
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _arg_is_bare_literal(raw_line: str, call_paren_idx: int) -> bool:
    """Return True if the first arg to a call is a single bare string literal.

    ``raw_line`` is the original (un-stripped) line. ``call_paren_idx`` is
    the index of the ``(`` opening the call. We test the substring
    starting at ``call_paren_idx`` against ``RE_BARE_LITERAL_ARG``.
    """
    sub = raw_line[call_paren_idx:]
    m = RE_BARE_LITERAL_ARG.match(sub)
    if not m:
        return False
    # Reject f-strings: an f / F prefix immediately before the quote.
    # The regex above already excludes f/F via the prefix class, so the
    # match implies no f-prefix, which is what we want.
    return True


def _find_call_paren(line: str, name_match: re.Match[str]) -> int:
    """Return the index of the ``(`` that opens the call matched by ``name_match``."""
    return name_match.end() - 1  # the regex consumes through the ``(``.


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        line = _strip_comment_and_strings(raw)

        # subprocess.<func>(..., shell=True, ...)
        m = RE_SUBPROCESS_CALL.search(line)
        if m and RE_SHELL_TRUE.search(line):
            paren = _find_call_paren(line, m)
            if not _arg_is_bare_literal(line, paren):
                findings.append(
                    (path, lineno, "subprocess-shell-true-interp", raw.rstrip())
                )
                continue

        # os.system(<expr>)  /  os.popen(<expr>)
        for kind_re, kind_name in (
            (RE_OS_SYSTEM, "os-system-interp"),
            (RE_OS_POPEN, "os-popen-interp"),
            (RE_COMMANDS_GET, "commands-getoutput-interp"),
        ):
            m2 = kind_re.search(line)
            if m2:
                paren = _find_call_paren(line, m2)
                if not _arg_is_bare_literal(line, paren):
                    findings.append((path, lineno, kind_name, raw.rstrip()))
                    break
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

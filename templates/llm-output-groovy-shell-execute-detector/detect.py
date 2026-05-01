#!/usr/bin/env python3
"""
llm-output-groovy-shell-execute-detector

Flags Groovy source where a String -- specifically a String built from
or interpolated with untrusted/dynamic input -- is sent to one of
Groovy's shell-spawning sinks:

  * "<cmd>".execute()           // GDK String#execute, /bin/sh -c style
  * ["sh", "-c", cmd].execute() // List form, but with a shell wrapper
  * Runtime.getRuntime().exec(cmd)   // when cmd is a single String
  * ProcessBuilder(cmd).start()      // when ctor arg is a single String
                                     // assembled from input

The single-String forms get tokenised by whitespace, so an attacker
who can inject quoting/spaces gets argv injection at minimum and full
shell metachar injection through ``execute()``. The List/Array form
with explicit ``["sh","-c", x]`` is the canonical "I asked for a
shell" anti-pattern -- also flagged.

Conservative heuristic: requires the string passed to the sink to
contain interpolation (``${...}`` / ``"$x"``), concatenation (`` + ``),
or to reference a known-tainted identifier (``params``, ``request``,
``args``, ``env``, ``System.getenv``, ``binding``, ``input``).

Stdlib only. Exit 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

_SUFFIXES = (".groovy", ".gvy", ".gradle", ".gsh", ".groovy.txt")

# Tokens that imply the value is influenceable by the caller.
_TAINT_HINTS = (
    "params",
    "request",
    "args[",
    "args.",
    "env[",
    "env.",
    "System.getenv",
    "binding",
    "input",
    "userInput",
    "${",
    '"$',     # GString shorthand: "$x foo"
    " + ",
)

# .execute() on a string-ish receiver.
_EXECUTE_RE = re.compile(
    r"""(?P<recv>(?:"[^"\n]*"|'[^'\n]*'|[A-Za-z_][\w.\[\]]*))
        \s*\.\s*execute\s*\(\s*\)""",
    re.VERBOSE,
)

# Runtime.getRuntime().exec( <single-string-arg> )
_RUNTIME_EXEC_RE = re.compile(
    r"Runtime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\(\s*(?P<arg>[^,)]+?)\s*\)"
)

# new ProcessBuilder( <single-string-arg> ).start() / no array literal
_PROCESS_BUILDER_RE = re.compile(
    r"new\s+ProcessBuilder\s*\(\s*(?P<arg>[^,)\[]+?)\s*\)"
)

# Explicit ["sh","-c", x].execute() -- always suspect.
_SH_C_LIST_RE = re.compile(
    r"""\[\s*["'](?:sh|bash|/bin/sh|/bin/bash|cmd(?:\.exe)?|powershell)["']
        \s*,\s*["']-c["']\s*,\s*(?P<arg>[^\]]+?)\s*\]
        \s*\.\s*execute\s*\(\s*\)""",
    re.VERBOSE | re.IGNORECASE,
)


def _looks_tainted(expr: str) -> bool:
    return any(h in expr for h in _TAINT_HINTS)


def _is_pure_string_literal(expr: str) -> bool:
    e = expr.strip()
    if (e.startswith('"') and e.endswith('"')
            and "${" not in e and '"$' not in e and "+" not in e):
        return True
    if (e.startswith("'") and e.endswith("'")
            and "+" not in e):
        return True
    return False


def _scan_text(text: str) -> List[Tuple[int, str, str]]:
    findings: List[Tuple[int, str, str]] = []
    lines = text.splitlines()

    # First pass: file-wide taint of locals.
    # An identifier is "tainted" if any RHS assignment to it contains
    # a taint hint (interpolation, concat, params/request/...).
    _ASSIGN_RE = re.compile(
        r"^\s*(?:def\s+|var\s+|String\s+|final\s+\w+\s+|@[\w.]+\s+)?"
        r"(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<rhs>.+)$"
    )
    tainted: set = set()
    for raw in lines:
        stripped = raw.lstrip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        m = _ASSIGN_RE.match(raw)
        if not m:
            continue
        rhs = m.group("rhs")
        if _looks_tainted(rhs):
            tainted.add(m.group("name"))

    def _arg_is_suspect(arg: str, line: str) -> bool:
        a = arg.strip()
        if _is_pure_string_literal(a):
            return False
        if a.startswith(("[", "{")):
            return False
        if _looks_tainted(a) or _looks_tainted(line):
            return True
        # Bare identifier: suspect if we saw it tainted above,
        # or if it has the shape of "single command string" (no Arr/Array/List suffix
        # and not all-caps constant).
        if re.fullmatch(r"[A-Za-z_]\w*", a):
            if a in tainted:
                return True
            if a.isupper():
                return False
            if a.endswith(("Arr", "Array", "List", "Argv", "Cmd_arr")):
                return False
        return False

    for lineno, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue

        for m in _SH_C_LIST_RE.finditer(line):
            findings.append(
                (lineno, "groovy-sh-c-list-execute", line.strip()[:140])
            )

        for m in _EXECUTE_RE.finditer(line):
            recv = m.group("recv")
            if _is_pure_string_literal(recv):
                continue
            if recv.startswith(('"', "'")):
                if not _looks_tainted(recv):
                    continue
            else:
                if not (_looks_tainted(recv) or _looks_tainted(line)
                        or recv in tainted):
                    continue
            findings.append(
                (lineno, "groovy-string-execute", line.strip()[:140])
            )

        for m in _RUNTIME_EXEC_RE.finditer(line):
            arg = m.group("arg")
            if _arg_is_suspect(arg, line):
                findings.append(
                    (lineno, "groovy-runtime-exec-string", line.strip()[:140])
                )

        for m in _PROCESS_BUILDER_RE.finditer(line):
            arg = m.group("arg")
            if _arg_is_suspect(arg, line):
                findings.append(
                    (lineno, "groovy-processbuilder-string", line.strip()[:140])
                )

    return findings


def _iter_files(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in files:
                    if name.endswith(_SUFFIXES):
                        yield os.path.join(root, name)
        else:
            yield p


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detect.py <file-or-dir> [more...]",
            file=sys.stderr,
        )
        return 2
    any_finding = False
    for path in _iter_files(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"{path}: read error: {exc}", file=sys.stderr)
            continue
        for line, label, snippet in _scan_text(text):
            any_finding = True
            print(f"{path}:{line}: {label}: {snippet}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""
llm-output-go-exec-command-injection-detector

Flags Go source where os/exec is invoked with a shell interpreter
(`sh -c`, `bash -c`, `cmd /C`, `powershell -Command`) and the command
string is built from concatenation, fmt.Sprintf with verbs, or string
addition. This is the canonical CWE-78 (OS Command Injection) shape
that LLMs love to emit when the user says "run this command for me".

Stdlib only. Reads files passed on argv (or recurses into directories).
Exit 0 = no findings, 1 = at least one finding, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# Match exec.Command(...) or exec.CommandContext(ctx, ...) calls.
_CALL_RE = re.compile(
    r"\bexec\.(?:Command|CommandContext)\s*\(",
)

# Shell interpreters whose second arg is parsed as a script.
_SHELL_BIN = re.compile(
    r"""['"](?:/usr/bin/|/bin/)?(?:sh|bash|zsh|ksh|dash|cmd(?:\.exe)?|powershell(?:\.exe)?|pwsh)['"]""",
    re.IGNORECASE,
)

# Flags that mean "next arg is a script string".
_SHELL_SCRIPT_FLAG = re.compile(
    r"""['"](?:-c|/C|/c|-Command|-EncodedCommand)['"]""",
)

# Signs that a string is built from variable input rather than being a literal.
_DYNAMIC_HINT = re.compile(
    r"""(?x)
    (?:
        fmt\.Sprintf\s*\(             # fmt.Sprintf("...", x)
        | \+\s*[A-Za-z_]               # "..." + var
        | [A-Za-z_]\w*\s*\+\s*['"]    # var + "..."
        | strings\.Join\s*\(           # strings.Join(parts, " ")
        | strings\.Replace(?:All)?\s*\(
    )
    """
)


def _split_top_level_args(s: str) -> List[str]:
    """Split a Go call's argument list on commas at paren-depth 0,
    respecting string literals. `s` is the text *inside* the outer ()."""
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in '"`':
            # consume string literal
            quote = c
            buf.append(c)
            i += 1
            while i < n:
                ch = s[i]
                buf.append(ch)
                if ch == "\\" and quote == '"' and i + 1 < n:
                    buf.append(s[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    i += 1
                    break
                i += 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_call_argstring(text: str, start: int) -> Tuple[str, int]:
    """Given `text` and the index of '(' opener (start points at '('),
    return (inside_text, index_after_close). Respects nested parens
    and string literals."""
    assert text[start] == "("
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c in '"`':
            quote = c
            i += 1
            while i < n:
                ch = text[i]
                if ch == "\\" and quote == '"' and i + 1 < n:
                    i += 2
                    continue
                if ch == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        i += 1
    return text[start + 1 :], n


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for m in _CALL_RE.finditer(text):
        paren_idx = m.end() - 1  # the '(' of exec.Command(
        inside, _ = _extract_call_argstring(text, paren_idx)
        args = _split_top_level_args(inside)
        # exec.CommandContext(ctx, name, args...) -> drop ctx
        if m.group(0).startswith("exec.CommandContext") and args:
            args = args[1:]
        if len(args) < 2:
            continue
        name_arg = args[0]
        if not _SHELL_BIN.search(name_arg):
            continue
        # Look for "-c" / "/C" / "-Command" then a dynamic script.
        for j in range(1, len(args) - 1):
            if _SHELL_SCRIPT_FLAG.search(args[j]):
                script_arg = args[j + 1]
                if _DYNAMIC_HINT.search(script_arg):
                    line_no = text.count("\n", 0, m.start()) + 1
                    findings.append(
                        f"{path}:{line_no}: exec.Command shell interpreter "
                        f"with dynamic script (CWE-78): "
                        f"flag={args[j]!s} script={script_arg[:80]!s}"
                    )
                    break
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(".go") or f.endswith(".go.txt"):
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

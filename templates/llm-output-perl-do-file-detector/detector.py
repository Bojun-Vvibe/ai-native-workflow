#!/usr/bin/env python3
"""Detect Perl `do FILE` / dynamic `require` sinks in LLM-generated `.pl`/`.pm`.

Perl's `do EXPR` (when EXPR is a *filename* — a scalar, an interpolated string,
or any non-block expression) reads the file, parses it as Perl, and evaluates
it in the current package. It is the file-based cousin of `eval STRING`. Any
attacker-influenced filename — fetched from the network, derived from user
input, looked up in `%ENV` — turns into RCE.

Similarly `require EXPR` with a *non-bareword* argument (a scalar variable,
interpolated string, etc.) loads and executes a Perl file at runtime by a
runtime-computed path. `require Module::Name` (a bareword) is normal Perl
and is NOT flagged.

This detector is single-pass, python3 stdlib only. It masks Perl line comments
(`# ...`), POD blocks (`=pod ... =cut`, `=head1 ... =cut`, etc.), and the
contents of single- and double-quoted strings, q/qq/qr/qw quote-likes, and
heredocs (best-effort: `<<TAG` ... `TAG`). After masking, regex patterns fire.

Sinks flagged:
  do-scalar         `do $path`
  do-interp-string  `do "...$var..."` or `do qq{... $var ...}`
  do-q-bracket      `do q{...}` / `do qq{...}` even if no interpolation
  do-paren-expr     `do(<glob>)` / `do(...)` non-block
  require-scalar    `require $module_path`
  require-interp    `require "Foo/$x.pm"`

`do { BLOCK }` (a control-flow construct, not a file load) is NOT flagged.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("do-scalar",        re.compile(r"\bdo\s+\$\w")),
    ("do-interp-string", re.compile(r'\bdo\s+"')),
    ("do-q-bracket",     re.compile(r"\bdo\s+q[qrw]?\s*[\{\[\(<]")),
    ("do-paren-expr",    re.compile(r"\bdo\s*\(")),
    ("require-scalar",   re.compile(r"\brequire\s+\$\w")),
    ("require-interp",   re.compile(r'\brequire\s+"')),
]

EXTS = {".pl", ".pm", ".t"}


def mask(src: str) -> str:
    """Blank comments / POD / string-literal interiors. Preserve newlines."""
    out: List[str] = []
    i, n = 0, len(src)
    in_pod = False
    in_str = False
    str_quote = ""
    in_qlike = False
    qlike_close = ""
    in_heredoc = False
    heredoc_tag = ""
    line_start = True

    def at_word_boundary(j: int) -> bool:
        if j == 0:
            return True
        prev = src[j - 1]
        return not (prev.isalnum() or prev == "_")

    while i < n:
        c = src[i]

        if in_pod:
            # POD ends with "=cut" at column 0 followed by newline-ish
            if line_start and src[i:i + 4] == "=cut":
                # blank the =cut line
                eol = src.find("\n", i)
                if eol == -1:
                    out.append(" " * (n - i))
                    i = n
                else:
                    out.append(" " * (eol - i))
                    i = eol
                in_pod = False
                line_start = False
                continue
            if c == "\n":
                out.append("\n")
                line_start = True
            else:
                out.append(" ")
                line_start = False
            i += 1
            continue

        if in_heredoc:
            if line_start and src[i:i + len(heredoc_tag)] == heredoc_tag:
                # check that the tag stands alone on the line
                end = i + len(heredoc_tag)
                if end == n or src[end] in ("\n", ";", " ", "\t"):
                    out.append(" " * len(heredoc_tag))
                    i = end
                    in_heredoc = False
                    heredoc_tag = ""
                    line_start = False
                    continue
            if c == "\n":
                out.append("\n")
                line_start = True
            else:
                out.append(" ")
                line_start = False
            i += 1
            continue

        if in_str:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == str_quote:
                in_str = False
                out.append(c)
                i += 1
                line_start = False
                continue
            out.append("\n" if c == "\n" else " ")
            if c == "\n":
                line_start = True
            i += 1
            continue

        if in_qlike:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == qlike_close:
                in_qlike = False
                out.append(c)
                i += 1
                line_start = False
                continue
            out.append("\n" if c == "\n" else " ")
            if c == "\n":
                line_start = True
            i += 1
            continue

        # Not in any masked region.
        # POD start: line begins with =word
        if line_start and c == "=" and i + 1 < n and src[i + 1].isalpha():
            in_pod = True
            out.append(" ")
            i += 1
            line_start = False
            continue

        if c == "#":
            eol = src.find("\n", i)
            if eol == -1:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (eol - i))
                i = eol
            continue

        # Heredoc detection: <<TAG or <<"TAG" or <<'TAG' or <<~TAG
        if c == "<" and src[i:i + 2] == "<<":
            m = re.match(r"<<(~?)(?:'([A-Za-z_]\w*)'|\"([A-Za-z_]\w*)\"|([A-Za-z_]\w*))", src[i:])
            if m:
                tag = m.group(2) or m.group(3) or m.group(4)
                # only treat as heredoc if next char after tag isn't part of
                # a shift operator's right side that is numeric/expr-like
                heredoc_tag = tag
                # consume the <<TAG token
                end = i + m.end()
                out.append(" " * (end - i))
                # rest of current line is normal code; heredoc starts after the newline
                # find newline
                nl = src.find("\n", end)
                if nl == -1:
                    i = end
                else:
                    out.append(src[end:nl])
                    out.append("\n")
                    i = nl + 1
                    line_start = True
                in_heredoc = True
                continue

        # quote-like operators: q{}, qq{}, qw{}, qr{}, with delim from {[(< or any non-alnum
        if c == "q" and i + 1 < n:
            m = re.match(r"q[qwr]?\s*([^\w\s])", src[i:])
            if m and at_word_boundary(i):
                op_len = m.end() - 1
                delim = m.group(1)
                close = {"{": "}", "[": "]", "(": ")", "<": ">"}.get(delim, delim)
                # preserve the prefix + opening delimiter so `do qq{...}` is
                # still detectable; only the body gets blanked.
                out.append(src[i:i + m.end()])
                qlike_close = close
                in_qlike = True
                i += m.end()
                line_start = False
                continue

        if c in ('"', "'", "`"):
            in_str = True
            str_quote = c
            out.append(c)
            i += 1
            line_start = False
            continue

        if c == "\n":
            out.append("\n")
            line_start = True
            i += 1
            continue

        out.append(c)
        line_start = False
        i += 1

    return "".join(out)


def scan_file(path: str) -> List[Tuple[int, int, str, str]]:
    findings: List[Tuple[int, int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
        return findings
    masked = mask(src)
    masked_lines = masked.splitlines()
    raw_lines = src.splitlines()
    for idx, m in enumerate(masked_lines):
        for name, pat in PATTERNS:
            mo = pat.search(m)
            if mo:
                col = mo.start() + 1
                snippet = raw_lines[idx].strip() if idx < len(raw_lines) else ""
                findings.append((idx + 1, col, name, snippet))
                break
    return findings


def walk(paths: Iterable[str]) -> Iterable[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    if os.path.splitext(f)[1] in EXTS:
                        yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def main(argv: List[str]) -> int:
    if not argv:
        print("usage: detector.py PATH [PATH ...]", file=sys.stderr)
        return 2
    total = 0
    for path in walk(argv):
        for lineno, col, name, snippet in scan_file(path):
            print(f"{path}:{lineno}:{col}: {name} {snippet}")
            total += 1
    print(f"-- {total} finding(s)", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Detect Perl shell-injection footguns: backtick command substitution,
``qx//`` operators, ``system($cmd)`` (single string), ``exec($cmd)``,
and ``open(FH, "$cmd|")`` / ``open(FH, "|$cmd")`` where ``$cmd``
contains an interpolated variable.

These are CWE-78 (OS Command Injection) classics. The safe shape is
the **list form** of ``system`` / ``exec`` / ``open``::

    system('git', 'log', '--', $path);          # safe
    open(my $fh, '-|', 'git', 'log', '--', $p); # safe

A LLM under pressure to "make it work" will instead emit::

    my $log = `git log -- $path`;               # injection
    system("git log -- $path");                 # injection
    open(my $fh, "git log -- $path|") or die;   # injection

The detector flags four kinds:

1. **perl-backticks-interp** — a `` `...` `` string containing a
   ``$var`` / ``@var`` interpolation, OR a ``qx{...}`` / ``qx(...)`` /
   ``qx[...]`` / ``qx<...>`` / ``qx/.../`` form with the same.
2. **perl-system-string** — ``system("...$x...")`` /
   ``system('...')`` where the single argument is a double-quoted
   string with interpolation. Single-quoted single-arg ``system`` is
   *not* flagged (no interpolation).
3. **perl-exec-string** — same shape for ``exec``.
4. **perl-open-pipe-interp** — ``open(... "$cmd|")`` or
   ``open(... "|$cmd")`` (two-arg form) where the mode/command string
   contains a pipe and an interpolated variable.

A finding is suppressed if the same logical line carries
``# llm-allow:perl-shell``. String literal interiors (other than the
shell strings being analyzed) and comments are NOT broadly masked
because Perl's quoting is operator-rich; instead, single-quoted
strings are individually skipped per shape.

Fenced ``pl`` / ``perl`` code blocks are extracted from Markdown.

Stdlib only. Exit code 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# llm-allow:perl-shell"

SCAN_SUFFIXES = (".pl", ".pm", ".t", ".md", ".markdown")


# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_PERL_LANGS = {"pl", "perl"}


def _iter_perl_blocks(text: str):
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _PERL_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Comment masking. Perl comments start with `#` (not inside strings) and
# run to EOL. We do NOT try to mask string interiors here; each shape's
# regex either handles single quotes itself or operates on a quoted
# context that already excludes them.
# ---------------------------------------------------------------------------


def _mask_comments(text: str) -> str:
    """Mask comments AND the interiors of `my $x = "..."` /
    `my $x = '...'` value strings on assignment / argument positions.

    We deliberately do NOT mask the shell-execution forms themselves
    (backticks, qx, the argument string of system()/exec()/open()) —
    the shape regexes run against this masked text and need those
    intact. The masker only neutralises *value* strings that follow
    `=`, `,`, `(`, `=>`, or `return`, where any inner `\\$x` /
    `system(...)` etc. is just a literal payload."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        # comment to EOL (heuristic)
        if c == "#":
            prev = text[i - 1] if i > 0 else "\n"
            if prev in " \t\n;{}(),=":
                j = text.find("\n", i)
                if j == -1:
                    j = n
                out.append(" " * (j - i))
                i = j
                continue
        # value-position string: scan back over whitespace; if the
        # previous non-space char is one of `= , ( { => return`, mask
        # the whole string body.
        if c == '"' or c == "'":
            k = i - 1
            while k >= 0 and text[k] in " \t":
                k -= 1
            prev_ch = text[k] if k >= 0 else "\n"
            is_value_pos = (
                prev_ch == "="
                and not (k >= 1 and text[k - 1] in "=!<>")  # not == != <= >=
            ) or (
                k >= 5 and text[k - 5:k + 1] == "return"
            ) or (k >= 1 and text[k - 1:k + 1] == "=>")
            if is_value_pos:
                quote = c
                out.append(quote)
                j = i + 1
                while j < n:
                    cj = text[j]
                    if cj == "\\" and j + 1 < n:
                        out.append("  ")
                        j += 2
                        continue
                    if cj == quote:
                        out.append(quote)
                        j += 1
                        break
                    out.append("\n" if cj == "\n" else " ")
                    j += 1
                i = j
                continue
        if c == "#":
            # Heuristic: only treat as comment if at start-of-line or
            # preceded by whitespace / `;` / `{` / `}` / `(` / `,`.
            prev = text[i - 1] if i > 0 else "\n"
            if prev in " \t\n;{}(),=":
                # consume to end of line
                j = text.find("\n", i)
                if j == -1:
                    j = n
                out.append(" " * (j - i))
                i = j
                continue
        out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Shape regexes (run on comment-masked text).
# ---------------------------------------------------------------------------


# Backticks containing $var / @var (avoid empty / pure-literal).
_BACKTICK_RE = re.compile(
    r"`[^`\n]*[\$@][A-Za-z_][\w:]*[^`\n]*`"
)

# qx with paired delimiters {} () [] <> or generic / / / | etc.
# We constrain to avoid eating the world: stop at first matching close
# (no nesting). Require interpolation.
_QX_PAIRS = [
    (r"\{", r"\}"),
    (r"\(", r"\)"),
    (r"\[", r"\]"),
    (r"<", r">"),
]
_QX_PAIR_RES = [
    re.compile(
        r"\bqx" + o + r"[^" + c.strip("\\") + r"\n]*?"
        r"[\$@][A-Za-z_][\w:]*[^" + c.strip("\\") + r"\n]*?" + c
    )
    for o, c in _QX_PAIRS
]
_QX_GENERIC_RE = re.compile(
    r"\bqx([!/|#~])(?:(?!\1).)*?[\$@][A-Za-z_][\w:]*(?:(?!\1).)*?\1"
)

# system("...$x...")  /  exec("...$x...")
# We require a double-quoted single-string argument that contains
# interpolation.  Multi-arg list form is not matched (good).
_SYSTEM_STR_RE = re.compile(
    r"\bsystem\s*\(\s*\"[^\"\n]*[\$@][A-Za-z_][\w:]*[^\"\n]*\"\s*\)"
)
_EXEC_STR_RE = re.compile(
    r"\bexec\s*\(\s*\"[^\"\n]*[\$@][A-Za-z_][\w:]*[^\"\n]*\"\s*\)"
)
# Also catch the parenthesis-less form: system "..."; / exec "...";
_SYSTEM_BARE_RE = re.compile(
    r"\bsystem\s+\"[^\"\n]*[\$@][A-Za-z_][\w:]*[^\"\n]*\"\s*;"
)
_EXEC_BARE_RE = re.compile(
    r"\bexec\s+\"[^\"\n]*[\$@][A-Za-z_][\w:]*[^\"\n]*\"\s*;"
)

# open(FH, "$cmd|") / open(FH, "|$cmd")  — two-arg form, pipe in mode.
_OPEN_PIPE_RE = re.compile(
    r"\bopen\s*\(\s*[^,]+,\s*"
    r"\"[^\"\n]*[\$@][A-Za-z_][\w:]*[^\"\n]*\"\s*\)"
)


def _line_of(text: str, idx: int, line_offset: int) -> int:
    return text.count("\n", 0, idx) + 1 + line_offset


def _suppressed(raw_lines: list[str], local_line: int) -> bool:
    if 1 <= local_line <= len(raw_lines):
        return SUPPRESS in raw_lines[local_line - 1]
    return False


def _scan_perl(
    raw: str,
    masked: str,
    raw_lines: list[str],
    line_offset: int,
    findings: list[tuple[int, str, str]],
) -> None:
    def add(pos: int, kind: str, msg: str) -> None:
        line = _line_of(masked, pos, line_offset)
        if _suppressed(raw_lines, line - line_offset):
            return
        findings.append((line, kind, msg))

    for m in _BACKTICK_RE.finditer(masked):
        add(m.start(), "perl-backticks-interp",
            "backticks with interpolated variable")
    for r in _QX_PAIR_RES:
        for m in r.finditer(masked):
            add(m.start(), "perl-backticks-interp",
                "qx{...} with interpolated variable")
    for m in _QX_GENERIC_RE.finditer(masked):
        add(m.start(), "perl-backticks-interp",
            "qx/.../ with interpolated variable")

    for m in _SYSTEM_STR_RE.finditer(masked):
        add(m.start(), "perl-system-string",
            "system() called with interpolated string — use list form")
    for m in _SYSTEM_BARE_RE.finditer(masked):
        add(m.start(), "perl-system-string",
            "system with interpolated string — use list form")
    for m in _EXEC_STR_RE.finditer(masked):
        add(m.start(), "perl-exec-string",
            "exec() called with interpolated string — use list form")
    for m in _EXEC_BARE_RE.finditer(masked):
        add(m.start(), "perl-exec-string",
            "exec with interpolated string — use list form")

    for m in _OPEN_PIPE_RE.finditer(masked):
        # Only flag if the mode string actually contains a `|`.
        snippet = masked[m.start():m.end()]
        if "|" in snippet:
            add(m.start(), "perl-open-pipe-interp",
                "open(FH, \"...|\") with interpolation — use 3+ arg "
                "list form: open($fh, '-|', @cmd)")


# ---------------------------------------------------------------------------
# File entrypoints.
# ---------------------------------------------------------------------------


def scan_text(text: str, suffix: str) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    if suffix in (".md", ".markdown"):
        for body, line_offset in _iter_perl_blocks(text):
            masked = _mask_comments(body)
            raw_lines = body.splitlines()
            _scan_perl(body, masked, raw_lines, line_offset, findings)
    else:
        masked = _mask_comments(text)
        raw_lines = text.splitlines()
        _scan_perl(text, masked, raw_lines, 0, findings)
    # Deduplicate identical (line, kind) pairs that can come from
    # overlapping regexes (e.g. paired-delim qx vs generic qx).
    seen = set()
    unique: list[tuple[int, str, str]] = []
    for f in sorted(findings, key=lambda t: (t[0], t[1], t[2])):
        key = (f[0], f[1], f[2])
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


def _iter_files(paths: list[str]):
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for sub in sorted(path.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SCAN_SUFFIXES:
                    yield sub
        elif path.is_file():
            if path.suffix.lower() in SCAN_SUFFIXES:
                yield path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    any_findings = False
    for f in _iter_files(argv[1:]):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"{f}: error reading: {exc}", file=sys.stderr)
            continue
        for line, kind, msg in scan_text(text, f.suffix.lower()):
            any_findings = True
            print(f"{f}:{line}: {kind}: {msg}")
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Detect dangerous xonsh `execx` / `evalx` invocations on dynamic strings.

xonsh is a Python-powered shell. Beyond Python's own `eval` and
`exec` (which the python-eval-detector covers), xonsh ships a pair
of subshell-aware builtins exposed in every xonsh script:

* `execx(SOURCE)`            — parse SOURCE as xonsh source (mixed
                                shell + python) and execute in the
                                current namespace
* `evalx(SOURCE)`            — parse SOURCE as a single xonsh
                                expression and return its value
* `__xonsh__.execer.exec(S)` — the lower-level entry point that
                                `execx` wraps; same blast radius
* `__xonsh__.execer.eval(S)` — same for `evalx`

When SOURCE is dynamic — built from `$ARG`, `${...}`, `@(...)`
substitutions, `$(cmd)` capture, `!(cmd)` exec, or any python
variable — the caller controls the next chunk of shell-with-python
to run. That covers BOTH OS command injection and arbitrary python
execution, which is strictly worse than a pure-shell `eval`.

What this flags
---------------
* `execx(ANYTHING_DYNAMIC)`
* `evalx(ANYTHING_DYNAMIC)`
* `__xonsh__.execer.exec(ANYTHING_DYNAMIC)`
* `__xonsh__.execer.eval(ANYTHING_DYNAMIC)`

"Dynamic" = the argument contains a name reference (any identifier
that is not a string/number literal), an f-string, a `%`-format,
a `.format(`, a `+` concatenation, or a xonsh `$VAR` / `${...}` /
`@(...)` / `$(...)` / `!(...)` substitution.

Out of scope (deliberately)
---------------------------
* Plain python `eval(` / `exec(` — covered by the python-eval-string
  detector family.
* `subprocess.run(..., shell=True)` — covered by the python-shell-true
  detector family.
* `compile(...)` followed by `exec(...)` — covered by the python-
  compile-exec detector.

Suppress an audited line with a trailing `# execx-ok` comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.xsh files, .xonshrc, and
files whose first line is a xonsh shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Each pattern matches the call NAME plus a `(`. We then look at the
# parenthesised argument to decide if it is dynamic.
RE_CALL = re.compile(
    r"\b(execx|evalx|__xonsh__\.execer\.exec|__xonsh__\.execer\.eval)\s*\("
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*execx-ok\b")

# Tokens inside the argument list that mean "this is dynamic".
# After comment+string scrubbing, any of these is sufficient:
#   * `$` for $VAR / ${VAR} / $(...) / $[...] / $(...) capture
#   * `@` for @(...) python-substitution and `@$(...)` glob
#   * `!` for !(...) / ![...] subprocess capture (only when followed
#     by `(` or `[` — plain logical-not `!=` is python and shouldn't
#     trigger)
#   * `f"` or `f'` f-string prefix (these survive scrubbing because
#     scrubbing happens AFTER we already collected the slice)
#   * `+`  string concatenation
#   * `%`  printf-style format
#   * `.format(`
#   * any bare identifier (we test for this last, with a regex that
#     skips python keywords + common literal tokens)
RE_DYN_SIGIL = re.compile(r"[$@]")
RE_DYN_BANG = re.compile(r"![\(\[]")
RE_DYN_FSTR = re.compile(r"\bf['\"]")
RE_DYN_FORMAT = re.compile(r"\.format\s*\(")
RE_DYN_PCT = re.compile(r"%\s*[a-zA-Z_(\[]")
RE_DYN_PLUS = re.compile(r"\+")
RE_IDENT = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*)\b")

PY_KEYWORDS = {
    "True", "False", "None", "and", "or", "not", "is", "in",
    "if", "else", "for", "lambda", "return", "yield",
}


def strip_comments_and_strings(text: str) -> str:
    """Blank `#` comment tails and the bodies of '...', "...", '''...''',
    and \"\"\"...\"\"\" string literals while preserving column positions.
    f-strings get their PREFIX kept (so the dynamic-arg test can spot
    `f"` later) but their body blanked. xonsh-specific `$(...)`,
    `${...}`, `@(...)`, `!(...)`, `![...]` are NOT string literals
    so they survive untouched."""
    out = list(text)
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # Comment to end of line.
        if ch == "#":
            j = i
            while j < n and text[j] != "\n":
                out[j] = " " if text[j] != "\n" else "\n"
                j += 1
            i = j
            continue
        # String literals — need to handle triple, single, with
        # optional `r`/`b`/`f`/`rb`/`br`/`fr`/`rf` prefix. Keep the
        # prefix character `f` so RE_DYN_FSTR can see it, but blank
        # the body so we don't false-positive on its contents.
        if ch in "rRbBfF" and i + 1 < n and text[i + 1] in "'\"":
            # prefix char — keep, advance past it
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            triple = (i + 2 < n and text[i + 1] == quote and text[i + 2] == quote)
            if triple:
                end = text.find(quote * 3, i + 3)
                if end == -1:
                    end = n
                else:
                    end += 3
                for k in range(i, end):
                    if text[k] != "\n":
                        out[k] = " "
                # keep the opening/closing quote chars themselves
                if i < n:
                    out[i] = quote
                if i + 1 < n:
                    out[i + 1] = quote
                if i + 2 < n:
                    out[i + 2] = quote
                if end - 1 < n:
                    out[end - 1] = quote
                if end - 2 < n:
                    out[end - 2] = quote
                if end - 3 < n:
                    out[end - 3] = quote
                i = end
                continue
            # single-line quoted
            j = i + 1
            while j < n and text[j] != quote and text[j] != "\n":
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                j += 1
            for k in range(i, min(j + 1, n)):
                if text[k] != "\n":
                    out[k] = " "
            if i < n:
                out[i] = quote
            if j < n:
                out[j] = quote
            i = j + 1 if j < n else n
            continue
        i += 1
    return "".join(out)


def find_matching_paren(text: str, open_idx: int) -> int:
    """Return index of `)` that closes the `(` at open_idx, or -1."""
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def is_dynamic_arg(arg_scrub: str, arg_raw: str) -> bool:
    if RE_DYN_SIGIL.search(arg_scrub):
        return True
    if RE_DYN_BANG.search(arg_scrub):
        return True
    if RE_DYN_FSTR.search(arg_raw):
        return True
    if RE_DYN_FORMAT.search(arg_scrub):
        return True
    if RE_DYN_PCT.search(arg_scrub):
        return True
    if RE_DYN_PLUS.search(arg_scrub):
        return True
    # Bare identifier reference (variable). Walk identifiers in the
    # scrubbed slice; reject keywords / literal-True/False/None.
    for m in RE_IDENT.finditer(arg_scrub):
        name = m.group(1)
        if name in PY_KEYWORDS:
            continue
        return True
    return False


def is_xonsh_file(path: Path) -> bool:
    if path.suffix == ".xsh":
        return True
    if path.name in (".xonshrc", "xonshrc"):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    return "xonsh" in first


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrub = strip_comments_and_strings(text)
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def offset_to_line_col(off: int) -> tuple[int, int]:
        # binary search would be nicer; linear is fine for any sane
        # source file size.
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, off - line_starts[lo] + 1

    for m in RE_CALL.finditer(scrub):
        name = m.group(1)
        open_idx = scrub.find("(", m.end() - 1)
        close_idx = find_matching_paren(scrub, open_idx)
        if close_idx == -1:
            continue
        arg_scrub = scrub[open_idx + 1:close_idx]
        arg_raw = text[open_idx + 1:close_idx]
        line_no, col = offset_to_line_col(m.start())
        # Honor suppression on the line where the call starts.
        line_text = text.splitlines()[line_no - 1] if line_no - 1 < len(text.splitlines()) else ""
        if RE_SUPPRESS.search(line_text):
            continue
        if not is_dynamic_arg(arg_scrub, arg_raw):
            continue
        kind = "xonsh-execx-dynamic" if "exec" in name else "xonsh-evalx-dynamic"
        findings.append((path, line_no, col, kind, line_text.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_xonsh_file(sub):
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

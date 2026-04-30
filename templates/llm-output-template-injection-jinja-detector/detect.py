#!/usr/bin/env python3
"""Detect server-side template-injection (SSTI) hazards in Python
code that calls Jinja2's `render_template_string`, `Template(...)`,
or `Environment.from_string(...)` with a **dynamic** template
source.

The Jinja2 sandbox is *not* enabled by default. When a Flask /
Quart / Sanic handler builds the template body from request data
(`request.args["x"]`, `f"Hello {name}"`, `"a" + user_input`,
`name % "...".format(name)` etc.) and hands it straight to
`render_template_string`, the attacker controls the entire template
AST: `{{ ''.__class__.__mro__[1].__subclasses__() }}` then walks
to `os.popen` and you get RCE. This is the canonical SSTI footgun
LLMs reproduce when asked to "render a greeting with the user's
name".

What this flags
---------------
* `render_template_string(EXPR)` where EXPR is not a single string
  literal (concatenation, f-string, `.format`, `%`, name reference,
  attribute access, subscript, function call).
* `Template(EXPR)` and `<env>.from_string(EXPR)` with the same
  dynamism test, when `Template` / `from_string` looks like the
  Jinja2 surface (heuristic: imported from `jinja2`, or the file
  also references `jinja2`).
* The match anchors on the *call site*, so `render_template_string`
  imported under an alias (`from flask import render_template_string
  as rts`) is not caught by name — flag the import instead by using
  the canonical name in your codebase, or rename in review.

What this does NOT flag
-----------------------
* `render_template_string("Hello {{ name }}", name=user)` — the
  template body is a literal; only the **context** is dynamic, and
  Jinja autoescaping keeps that safe for HTML output.
* `render_template("page.html", ...)` — file-backed templates are
  developer-controlled.
* Lines marked with a trailing `# ssti-ok` comment.
* Occurrences inside `#` comments or string literals (so the
  detector does not flag its own docstring).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Call sites we care about. We match the function name + opening
# paren and then capture the argument list up to the matching close
# paren on the same logical line (after string/comment scrubbing).
RE_CALL = re.compile(
    r"\b(render_template_string|from_string|Template)\s*\("
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"#\s*ssti-ok\b")

# A "pure literal" first argument: an optionally-prefixed string
# literal, possibly followed by `,` and more args, possibly followed
# by `)`. We're permissive on the string prefix (`r`, `b`, `u`, `f`
# is excluded — f-strings are dynamic).
RE_LITERAL_FIRST_ARG = re.compile(
    r"""^
        (?:[rRbBuU]{0,2})            # allowed string prefixes (no f/F)
        (?P<q>'''|\"\"\"|'|\")       # opening quote
        (?:\\.|(?!(?P=q)).)*         # body
        (?P=q)                       # matching close
        \s*$                         # nothing after
    """,
    re.VERBOSE | re.DOTALL,
)


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Replace the *contents* of Python string literals and `#`
    comment tails with spaces, preserving column positions and
    keeping the opening/closing quote characters in place.

    `in_triple` is the active triple-quote delimiter carried over
    from a previous line (`'''` or `\"\"\"`) or None. Returns
    `(scrubbed_line, new_in_triple)`.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple  # active quote token
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append(line[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if line[i:i + len(in_str)] == in_str:
            out.append(in_str)
            i += len(in_str)
            in_str = None
            continue
        out.append(" ")
        i += 1
    # If we end the line still inside a single-quoted string, treat
    # it as closed (Python would have raised) — only carry triple.
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def extract_first_arg(scrubbed: str, start: int) -> tuple[str, int] | None:
    """Given `scrubbed` and the index of the `(` after the call
    name, return `(first_arg_text, end_paren_index)` for the matched
    parenthesis. Returns None if the parens are unbalanced on this
    line (the scanner then skips this call).

    The first arg is everything up to the top-level `,` or the
    matching `)`.
    """
    depth = 0
    first_comma = -1
    end = -1
    for j in range(start, len(scrubbed)):
        ch = scrubbed[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = j
                break
        elif ch == "," and depth == 1 and first_comma < 0:
            first_comma = j
    if end < 0:
        return None
    arg_end = first_comma if first_comma > 0 else end
    return scrubbed[start + 1:arg_end], end


def first_arg_is_literal(text_scrubbed: str, text_raw: str, start: int) -> bool:
    """Decide whether the first call argument is a single safe
    string literal. We re-read the *raw* slice so we can detect
    `f"..."` (dynamic) vs `r"..."` (literal).
    """
    info = extract_first_arg(text_scrubbed, start)
    if info is None:
        # unbalanced — be conservative, treat as dynamic
        return False
    _, end = info
    comma = text_scrubbed.find(",", start, end)
    arg_end = comma if comma >= 0 else end
    raw_arg = text_raw[start + 1:arg_end]
    stripped = raw_arg.strip()
    if not stripped:
        return False
    # f-string prefix anywhere -> dynamic
    m = re.match(r"^([rRbBuUfF]{0,2})(['\"])", stripped)
    if m and ("f" in m.group(1).lower()):
        return False
    if RE_LITERAL_FIRST_ARG.match(stripped):
        return True
    return False


RE_JINJA_IMPORT = re.compile(
    r"(?m)^\s*(?:from\s+jinja2\b|import\s+jinja2\b)"
)


def file_uses_jinja(text: str) -> bool:
    return bool(RE_JINJA_IMPORT.search(text))


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    file_jinja = file_uses_jinja(text)
    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue
        # If the entire line was inside a multi-line triple-quoted
        # string when we entered, no real code on this line.
        for m in RE_CALL.finditer(scrub):
            name = m.group(1)
            if name in ("Template", "from_string") and not file_jinja:
                continue
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            if first_arg_is_literal(scrub, raw, paren):
                continue
            col = m.start() + 1
            kind = "jinja-ssti-dynamic-template"
            findings.append((path, idx, col, kind, raw.strip()))
    return findings


def is_python_file(path: Path) -> bool:
    if path.suffix == ".py":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!") and "python" in first


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_python_file(sub):
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

#!/usr/bin/env python3
r"""Detect Crystal macro `{{ run("...") }}` / `{{ system("...") }}` sites.

Crystal's macro language runs at *compile time*. The `run` macro method
compiles and executes a Crystal program at compile time and substitutes
its stdout into the AST:

    {{ run("./helpers/codegen", env_var) }}

The `system` macro method shells out at compile time:

    {% sys = `uname -a` %}
    {{ system("echo " + name) }}

Both are legitimate metaprogramming primitives, but they give an
attacker who controls the macro arguments (or the program path) full
build-time code execution. LLM-emitted Crystal code reaches for
`{{ run(...) }}` whenever the model is unsure how to express
compile-time codegen and almost never reasons about the source-of-truth
for the path / arguments.

What this flags
---------------
* `{{ run("...") }}`               — explicit macro `run` call
* `{{ run(path, *args) }}`         — non-literal arguments
* `{{ system("...") }}`            — `system` macro shell-out
* `{% ... = `cmd` %}`              — backtick command in a macro block
* `{{ `cmd` }}`                    — backtick command in interpolation

Suppression
-----------
Append `# macro-run-ok` to the line to silence a known-safe usage.

Out of scope (deliberately)
---------------------------
* Runtime `Process.run`, `system`, backtick `\`...\`` *outside* of
  macro brackets. Those are normal shell-out calls covered by other
  detectors.
* `{{ ... }}` interpolations that don't include `run` / `system` /
  backticks (e.g. `{{ @type }}`).

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.cr`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"#\s*macro-run-ok\b")

# Inside a macro interpolation `{{ ... }}` or directive `{% ... %}`,
# look for `run(`, `system(`, or a backtick command. We match the
# *opening* of the macro bracket and anything up to its closing.
RE_MACRO_BLOCK = re.compile(r"\{[{%].*?[%}]\}", re.DOTALL)

RE_RUN_CALL = re.compile(r"\brun\s*\(")
RE_SYSTEM_CALL = re.compile(r"\bsystem\s*\(")
RE_BACKTICK = re.compile(r"`[^`\n]*`")


def mask_crystal_comments_and_strings(text: str) -> str:
    """Mask Crystal `#` line comments and `"..."` string contents while
    preserving column positions and newlines.

    Crystal also has `<<-HEREDOC` and `<<-'HEREDOC'` heredocs; we mask
    `# ...` line comments and double-quoted strings (the only forms
    where a stray `{{ run(` token could falsely appear). Macro brackets
    `{{ }}` and `{% %}` are intentionally NOT masked — they are the
    target.

    The masker preserves macro brackets that appear inside string
    interpolation `"#{ ... }"` because Crystal evaluates those at
    runtime, not compile time, so a `run(` token there would NOT be
    a macro `run`. We therefore mask string contents wholesale,
    including any `#{...}` interior.
    """
    out = list(text)
    n = len(text)
    i = 0
    in_string = False
    string_quote = ""
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_string:
            if ch == "\\" and i + 1 < n:
                out[i] = " "
                out[i + 1] = " " if text[i + 1] != "\n" else "\n"
                i += 2
                continue
            if ch == string_quote:
                in_string = False
                i += 1
                continue
            out[i] = " " if ch != "\n" else "\n"
            i += 1
            continue
        # `#` line comment, but only when not part of a `#{` interp
        # opener (we already handle interp by being inside a string).
        if ch == "#":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        # Double-quoted string start
        if ch == '"':
            in_string = True
            string_quote = '"'
            i += 1
            continue
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    masked = mask_crystal_comments_and_strings(text)
    raw_lines = text.splitlines()
    # Walk macro blocks across the masked text so we keep accurate
    # offsets for line/column reporting.
    line_starts = [0]
    for idx, ch in enumerate(masked):
        if ch == "\n":
            line_starts.append(idx + 1)

    def offset_to_linecol(off: int) -> tuple[int, int]:
        # binary search would be nicer; linear is fine for examples.
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, off - line_starts[lo] + 1

    for block in RE_MACRO_BLOCK.finditer(masked):
        block_text = block.group(0)
        block_start = block.start()
        for sub in RE_RUN_CALL.finditer(block_text):
            abs_off = block_start + sub.start()
            line, col = offset_to_linecol(abs_off)
            raw = raw_lines[line - 1] if line - 1 < len(raw_lines) else ""
            if RE_SUPPRESS.search(raw):
                continue
            findings.append(
                (path, line, col, "crystal-macro-run", raw.strip())
            )
        for sub in RE_SYSTEM_CALL.finditer(block_text):
            abs_off = block_start + sub.start()
            line, col = offset_to_linecol(abs_off)
            raw = raw_lines[line - 1] if line - 1 < len(raw_lines) else ""
            if RE_SUPPRESS.search(raw):
                continue
            findings.append(
                (path, line, col, "crystal-macro-system", raw.strip())
            )
        for sub in RE_BACKTICK.finditer(block_text):
            abs_off = block_start + sub.start()
            line, col = offset_to_linecol(abs_off)
            raw = raw_lines[line - 1] if line - 1 < len(raw_lines) else ""
            if RE_SUPPRESS.search(raw):
                continue
            findings.append(
                (path, line, col, "crystal-macro-backtick", raw.strip())
            )
    return findings


def is_crystal_file(path: Path) -> bool:
    return path.suffix == ".cr"


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_crystal_file(sub):
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

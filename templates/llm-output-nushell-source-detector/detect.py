#!/usr/bin/env python3
"""Detect dynamic `source` / `source-env` / `nu -c` invocations in Nushell.

Nushell's `source FILE` and `source-env FILE` parse and execute the
contents of FILE in the current scope at evaluation time. When FILE is
not a constant string literal (i.e. it is a variable, an expression
involving `$nu.*`, the result of `($env.X | str ...)`, an interpolated
string `$"..."` containing `($var)`, or any subexpression), the script
that gets executed is no longer audit-controlled. That makes
`source $cfg` semantically the same as `eval` over the contents of
whatever path/string `$cfg` resolved to.

Likewise, `nu -c $cmd` (or `nu --commands $cmd`) re-enters the Nushell
parser on a string from a variable; an LLM that builds that string by
joining user input has just constructed a code-injection sink.

LLM-emitted Nushell frequently does:

* `source $cfg`                      — variable into source, UNSAFE
* `source-env $env.NU_LIB_DIRS`      — env-derived path, UNSAFE
* `source $"($pwd)/init.nu"`         — interpolated path, UNSAFE
* `nu -c $cmd`                       — variable into -c, UNSAFE
* `nu --commands $"build ($target)"` — interpolated -c, UNSAFE

The safe forms are: a bare-string literal path (`source ./init.nu`),
or a `const`-bound path proven constant at parse time. Anything else
should be rewritten to call a known module function with typed args.

What this flags
---------------
A `source`, `source-env`, or `nu` token at command position whose
first significant argument is NOT a bareword path or a plain
single-/double-quoted string literal without `$`-interpolation.

* `source $cfg`                                       — flagged
* `source-env $env.X`                                 — flagged
* `source $"($base)/x.nu"`                            — flagged (interp)
* `source ($cfg | str trim)`                          — flagged (paren expr)
* `nu -c $cmd`                                        — flagged
* `nu --commands $"do ($x)"`                          — flagged
* `source ./init.nu`                                  — NOT flagged
* `source "config/init.nu"`                           — NOT flagged
* `source 'config/init.nu'`                           — NOT flagged

Out of scope (deliberately)
---------------------------
* `use $mod`, `overlay use $name` — also dynamic but different semantics.
* `^nu -c ...` external invocation chain — caller's responsibility.
* We do not try to prove a variable is constant.

Suppress an audited line with a trailing `# source-ok` (or
`# nu-c-ok` for `nu -c` lines) comment.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.nu and files whose first line
is a `nu` shebang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# A "safe literal" first argument is:
#   - a bareword path that does NOT start with `$` or `(` and contains
#     no `$` interpolation, OR
#   - a single- or double-quoted string with no `$` inside (so no
#     interpolation), OR
#   - end-of-line / pipe / redirect (no arg yet).
#
# Anything else (starts with `$`, starts with `(`, `$"..."` form,
# `"...$x..."`, `'...'` is fine, etc.) is "dynamic".

# A safe arg literal: either single-quoted (no $ allowed inside even
# though nu does not interpolate inside '...'), or double-quoted with
# no `$`, or a bareword starting with [A-Za-z0-9_./-] (no $, no `(`,
# no `"`, no `$"`).
SAFE_ARG = re.compile(
    r"""(?x)
    (?:
        '[^']*'                          # single-quoted literal
      | "[^"$]*"                         # double-quoted with no $
      | [A-Za-z0-9_./~+\-][\w./~+\-]*   # bareword path/identifier
    )
    """
)

# Match `source` or `source-env` at command position followed by an arg.
RE_SOURCE = re.compile(
    r"(?:^|(?<=[;|]))\s*(source(?:-env)?)\b\s+(\S.*?)(?=$|;|\|)"
)

# Match `nu` followed somewhere by `-c` or `--commands` and an arg.
# We do not require command position because nu is often used in
# pipelines like `... | nu -c ...`. We do require a token boundary.
RE_NU_C = re.compile(
    r"(?:^|(?<=[\s;|(]))nu\b[^\n#]*?\s(-c|--commands)\b\s+(\S.*?)(?=$|;|\|)"
)

# Suppression markers.
RE_SUPPRESS_SOURCE = re.compile(r"#\s*source-ok\b")
RE_SUPPRESS_NUC = re.compile(r"#\s*nu-c-ok\b")


def strip_comments(line: str) -> str:
    """Blank out `#`-comment tail while preserving column positions.
    Nushell uses `#` for line comments. Inside a string literal (`"..."`
    or `'...'`) `#` is data, not a comment. We track string state and
    keep string contents intact (we need them to evaluate the arg of
    `source`)."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_dq = False
    in_sq = False
    while i < n:
        ch = line[i]
        if not in_dq and not in_sq:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch == '"':
                in_dq = True
            elif ch == "'":
                in_sq = True
            out.append(ch)
            i += 1
            continue
        # inside a string
        if in_dq and ch == "\\" and i + 1 < n:
            out.append(line[i : i + 2])
            i += 2
            continue
        if in_dq and ch == '"':
            in_dq = False
        elif in_sq and ch == "'":
            in_sq = False
        out.append(ch)
        i += 1
    return "".join(out)


def first_arg_is_safe(arg_blob: str) -> bool:
    """Return True if the first whitespace-separated token in arg_blob
    is a safe literal per SAFE_ARG. Empty arg blob is treated as "no
    arg" — not safe (we won't flag it because the regex requires \\S)."""
    s = arg_blob.lstrip()
    if not s:
        return False
    m = SAFE_ARG.match(s)
    if not m:
        return False
    # The match must be terminated by whitespace, end, pipe, semi, or
    # `;`. If the literal is followed by more identifier/expr chars,
    # then the bareword is actually longer and could still be a path —
    # but if it starts with `$` or `(` we already failed SAFE_ARG.
    end = m.end()
    if end >= len(s):
        return True
    nxt = s[end]
    return nxt.isspace() or nxt in (";", "|", "#")


def is_nushell_file(path: Path) -> bool:
    if path.suffix == ".nu":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    if not first.startswith("#!"):
        return False
    # Match `nu`, `nushell`, `/usr/bin/env nu`, etc., but not `nuke`.
    return bool(re.search(r"\b(nu|nushell)\b", first))


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub = strip_comments(raw)

        if not RE_SUPPRESS_SOURCE.search(raw):
            for m in RE_SOURCE.finditer(scrub):
                kw = m.group(1)
                arg = m.group(2)
                if not first_arg_is_safe(arg):
                    findings.append(
                        (path, idx, m.start(1) + 1, f"nushell-{kw}-dynamic", raw.strip())
                    )

        if not RE_SUPPRESS_NUC.search(raw):
            for m in RE_NU_C.finditer(scrub):
                arg = m.group(2)
                if not first_arg_is_safe(arg):
                    findings.append(
                        (path, idx, m.start(1) + 1, "nushell-nu-c-dynamic", raw.strip())
                    )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_nushell_file(sub):
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

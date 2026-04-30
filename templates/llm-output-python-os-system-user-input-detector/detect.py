#!/usr/bin/env python3
"""Detect os.system / os.popen calls built from interpolated input.

`os.system()` and `os.popen()` (and the legacy `os.popen2/3/4`,
`commands.getoutput`, and `popen2.popen*` shapes) hand the entire
argument to `/bin/sh -c`, which means any caller-controlled
substring becomes shell-syntax-active. Combined with f-strings,
`%`-formatting, `.format()`, or `+` concatenation, this is the
canonical command-injection footgun.

What this flags
---------------
* `os.system(f"... {x} ...")`            — f-string interpolation
* `os.system("..." + x + "...")`         — string concatenation
* `os.system("... %s ..." % x)`          — printf-style formatting
* `os.system("... {} ...".format(x))`    — str.format formatting
* same patterns for `os.popen`, `os.popen2`, `os.popen3`,
  `os.popen4`, `commands.getoutput`, `commands.getstatusoutput`,
  `popen2.popen2/3/4`

What this does NOT flag
-----------------------
* Plain string-literal arguments with no interpolation, e.g.
  `os.system("ls -la /tmp")` — still bad practice but a
  different class of finding (suggest `subprocess.run([...])`).
  This detector intentionally narrows to the user-input shape
  because that is the security-critical signal.
* `subprocess.run(["cmd", arg])` and other argv-list shapes —
  those are the safe replacement.
* Lines marked with a trailing `# os-system-ok` comment.
* Occurrences inside `#` comments and string literals.

Finding kinds
-------------
* `os-system-fstring`
* `os-system-concat`
* `os-system-percent`
* `os-system-format`

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


VULN_FUNCS = (
    r"os\s*\.\s*system"
    r"|os\s*\.\s*popen[234]?"
    r"|commands\s*\.\s*getoutput"
    r"|commands\s*\.\s*getstatusoutput"
    r"|popen2\s*\.\s*popen[234]"
)

# Match the call up to its opening paren; we then walk the args
# manually to handle nested parens robustly.
RE_CALL_HEAD = re.compile(rf"\b(?P<func>{VULN_FUNCS})\s*\(")

RE_SUPPRESS = re.compile(r"#\s*os-system-ok\b")

RE_FSTRING = re.compile(r"""(?P<q>[fFrRbB]*[fF][fFrRbB]*)\s*['"]""")
# We only inspect the args text after string-stripping for + / % /
# .format. f-strings are detected on the RAW arg text because the
# string-stripper would erase them.
RE_PERCENT_FMT = re.compile(r"%\s*[a-zA-Z(]")  # rough but ok inside arg text
RE_DOTFORMAT = re.compile(r"\.\s*format\s*\(")
RE_CONCAT_VAR = re.compile(
    r"['\"]\s*\+\s*[A-Za-z_]"      # "literal" + var
    r"|[A-Za-z_)\]]\s*\+\s*['\"]"  # var + "literal"
)


def strip_strings_for_lineop(text: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Blank out string contents (including triple-quoted) and `#` comments
    so plain operators like `+` / `%` / `.format` outside strings can be
    detected, while preserving the original character positions."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str: str | None = in_triple
    while i < n:
        ch = text[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if text[i:i + 3] in ("'''", '"""'):
                    in_str = text[i:i + 3]
                    out.append(text[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if text[i:i + len(in_str)] == in_str:
            out.append(in_str)
            i += len(in_str)
            in_str = None
            continue
        out.append(" ")
        i += 1
    return "".join(out), in_str


def extract_call_args(s: str, paren_idx: int) -> tuple[str, int] | None:
    """Return (arg_text, end_idx) for the call whose `(` is at paren_idx,
    operating on a string with `s` already comment-stripped but with
    string contents preserved (we still need them for the f-string
    regex). Tracks string literals to skip parens inside them."""
    depth = 0
    i = paren_idx
    n = len(s)
    in_str: str | None = None
    while i < n:
        ch = s[i]
        if in_str is None:
            if ch in ("'", '"'):
                if s[i:i + 3] in ("'''", '"""'):
                    in_str = s[i:i + 3]
                    i += 3
                    continue
                in_str = ch
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return s[paren_idx + 1:i], i
            i += 1
            continue
        # in string
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            i += 2
            continue
        if s[i:i + len(in_str)] == in_str:
            i += len(in_str)
            in_str = None
            continue
        i += 1
    return None


def classify_arg(raw_arg: str) -> str | None:
    """Return finding kind or None if the arg looks like a plain literal /
    plain identifier (no interpolation)."""
    # f-string detection on raw arg.
    # An f-string opens with a prefix containing 'f' or 'F' followed by
    # a quote. Check for a prefix token followed by ' or ".
    for m in re.finditer(r"\b([rRbB]*[fF][rRbB]*)\s*(['\"])", raw_arg):
        # Make sure this isn't preceded by an alphanumeric (would be
        # part of an identifier, not a string prefix).
        start = m.start(1)
        if start == 0 or not raw_arg[start - 1].isalnum():
            return "os-system-fstring"

    # Strip string contents to find operators outside literals.
    scrubbed, _ = strip_strings_for_lineop(raw_arg)

    if RE_DOTFORMAT.search(scrubbed):
        return "os-system-format"
    # `+` between something and a string literal (or vice versa).
    # We approximate by checking concat in original raw_arg, since
    # the literal disappears in scrubbed. But we still want to
    # require the `+` to be outside a string — which we get by
    # checking the scrubbed view has a `+`.
    if "+" in scrubbed and RE_CONCAT_VAR.search(raw_arg):
        return "os-system-concat"
    # `%` formatting: a `%` outside a string, with a string literal
    # on either side.
    if "%" in scrubbed and re.search(r"['\"][^'\"]*%[a-zA-Z][^'\"]*['\"]", raw_arg):
        return "os-system-percent"
    return None


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        # Track triple-quoted state across lines using the scrub fn,
        # but operate on a per-line copy with comments removed.
        scrubbed_line, in_triple = strip_strings_for_lineop(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue

        # Find call heads in the comment-stripped view.
        for m in RE_CALL_HEAD.finditer(scrubbed_line):
            paren_idx = m.end() - 1  # index of '(' in scrubbed_line
            # Pull args from the ORIGINAL raw line so f-string prefixes
            # survive. The paren index is the same because scrubbing
            # preserves character positions.
            ext = extract_call_args(raw, paren_idx)
            if ext is None:
                continue
            arg_text, _end = ext
            kind = classify_arg(arg_text)
            if kind is None:
                continue
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
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


def iter_targets(roots):
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

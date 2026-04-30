#!/usr/bin/env python3
"""Detect dangerous `subprocess` calls with `shell=True`.

Python's `subprocess.run`, `Popen`, `call`, `check_call`, and
`check_output` all accept a `shell=True` keyword. When that flag
is set, the first positional argument is handed to `/bin/sh -c`
(or `cmd.exe /c` on Windows) for word-splitting and metachar
interpretation. If any portion of that string is built from
external input — even via f-strings, `%` formatting, or `+`
concatenation — the result is a textbook command-injection
sink: an attacker who controls the interpolated value can chain
`;`, `|`, backticks, `$(...)`, or shell redirects.

LLMs reach for `shell=True` constantly because it is the path of
least resistance when the prompt says "run this command". The
correct call shape is almost always `subprocess.run(["cmd",
"arg"], shell=False)`, with arguments as a list and no shell
involved.

What this flags
---------------
* `subprocess.run(..., shell=True)` and friends where the
  command argument is *not* a plain string literal — i.e. it
  contains an f-string prefix, `%`-formatting, `.format(`, or
  `+` concatenation, or is a bare name / attribute / call.
* `os.system(<non-literal>)` — `os.system` is `shell=True` by
  definition, so any non-literal argument is flagged.
* `os.popen(<non-literal>)` for the same reason.
* `commands.getoutput` / `commands.getstatusoutput` (legacy
  Python 2 API still surfaced by some LLM training data).

What this does NOT flag
-----------------------
* `subprocess.run(["ls", "-la"])` — list form, no shell.
* `subprocess.run("ls -la", shell=True)` — pure string literal
  with no interpolation. Still smelly, but not an injection
  sink. The shell-true detector is conservative on purpose; pair
  it with a separate "shell=True at all" lint if you want to be
  stricter.
* `os.system("uptime")` — pure literal.
* Lines marked with a trailing `# shell-true-ok` comment.
* Occurrences inside `#` comments or string literals.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files (and python
shebang files).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# subprocess.<func>( ... shell=True ... )
RE_SUBPROCESS = re.compile(
    r"\bsubprocess\s*\.\s*(run|Popen|call|check_call|check_output)\s*\("
)

# Standalone os.system / os.popen / commands.getoutput*.
RE_OS_SYSTEM = re.compile(r"\bos\s*\.\s*system\s*\(")
RE_OS_POPEN = re.compile(r"\bos\s*\.\s*popen\s*\(")
RE_COMMANDS = re.compile(
    r"\bcommands\s*\.\s*(getoutput|getstatusoutput)\s*\("
)

RE_SHELL_TRUE = re.compile(r"\bshell\s*=\s*True\b")
RE_SUPPRESS = re.compile(r"#\s*shell-true-ok\b")

# Heuristics for "first arg is interpolated / dynamic".
RE_FSTRING = re.compile(r"""(?:^|[^A-Za-z0-9_])[fF][rR]?['"]""")
RE_FORMAT_CALL = re.compile(r"\.\s*format\s*\(")
RE_PERCENT_FMT = re.compile(r"%\s*[\(A-Za-z0-9_]")
RE_PLUS_CONCAT = re.compile(r"['\"]\s*\+|\+\s*['\"]")
# A bare identifier / attribute / call (no surrounding quotes at all).
RE_BARE_NAME = re.compile(r"^\s*[A-Za-z_][\w\.\[\]]*\s*(?:\(.*\))?\s*$")
# A pure string literal: starts and ends with matching quote, and
# the characters in between contain no unescaped quotes of the
# same kind. Good enough for single-line literals.
RE_PURE_STR = re.compile(
    r"""^\s*(?:[bBuU])?[rR]?(['"])(?:\\.|(?!\1).)*\1\s*$"""
)


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Blank Python comment tails and string literal contents,
    preserving column positions and quote tokens. Carries
    triple-quoted string state across lines.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
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
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def extract_call_args(scrubbed: str, paren_idx: int) -> str | None:
    depth = 0
    for j in range(paren_idx, len(scrubbed)):
        ch = scrubbed[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return scrubbed[paren_idx + 1:j]
    return None


def first_arg(args_text: str, raw_args_text: str) -> tuple[str, str]:
    """Return (scrubbed_first_arg, raw_first_arg) — text up to
    the first top-level comma. Operates on the scrubbed text so
    commas inside literals don't fool us, then mirrors the slice
    against the raw text for interpolation detection.
    """
    depth = 0
    end = len(args_text)
    for j, ch in enumerate(args_text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            end = j
            break
    return args_text[:end].strip(), raw_args_text[:end].strip()


def looks_dynamic(raw_arg: str) -> bool:
    """True if the raw first argument looks interpolated /
    non-literal."""
    if not raw_arg:
        return False
    if RE_PURE_STR.match(raw_arg):
        return False
    if RE_FSTRING.search(" " + raw_arg):
        return True
    if RE_FORMAT_CALL.search(raw_arg):
        return True
    if RE_PERCENT_FMT.search(raw_arg):
        return True
    if RE_PLUS_CONCAT.search(raw_arg):
        return True
    if RE_BARE_NAME.match(raw_arg):
        return True
    # Fallback: anything that isn't a clean literal and contains
    # no quotes at all is also dynamic.
    if "'" not in raw_arg and '"' not in raw_arg:
        return True
    return False


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue

        # subprocess.<func>(...).
        for m in RE_SUBPROCESS.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            if not RE_SHELL_TRUE.search(args):
                continue
            raw_args = raw[paren + 1:paren + 1 + len(args)]
            _, raw_first = first_arg(args, raw_args)
            if looks_dynamic(raw_first):
                kind = f"subprocess-{m.group(1)}-shell-true-dynamic"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))

        # os.system(...).
        for m in RE_OS_SYSTEM.finditer(scrub):
            paren = m.end() - 1
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            raw_args = raw[paren + 1:paren + 1 + len(args)]
            _, raw_first = first_arg(args, raw_args)
            if looks_dynamic(raw_first):
                findings.append((path, idx, m.start() + 1,
                                 "os-system-dynamic", raw.strip()))

        # os.popen(...).
        for m in RE_OS_POPEN.finditer(scrub):
            paren = m.end() - 1
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            raw_args = raw[paren + 1:paren + 1 + len(args)]
            _, raw_first = first_arg(args, raw_args)
            if looks_dynamic(raw_first):
                findings.append((path, idx, m.start() + 1,
                                 "os-popen-dynamic", raw.strip()))

        # commands.getoutput / commands.getstatusoutput.
        for m in RE_COMMANDS.finditer(scrub):
            paren = scrub.find("(", m.start())
            if paren < 0:
                continue
            args = extract_call_args(scrub, paren)
            if args is None:
                continue
            raw_args = raw[paren + 1:paren + 1 + len(args)]
            _, raw_first = first_arg(args, raw_args)
            if looks_dynamic(raw_first):
                kind = f"commands-{m.group(1)}-dynamic"
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

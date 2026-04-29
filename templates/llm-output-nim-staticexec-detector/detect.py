#!/usr/bin/env python3
"""Detect Nim compile-time shell-out and dynamic-include sinks.

Nim ships a family of compile-time facilities that execute arbitrary
host commands or splice arbitrary text into the program at compile
time. The dangerous five:

* `staticExec(STRING)`           — runs `sh -c STRING` on the build host
* `gorge(STRING)`                — alias of staticExec, returns stdout
* `gorgeEx(STRING, ...)`         — staticExec with stdin + stderr
* `staticRead(PATH)`             — slurps an arbitrary file at compile time
* `{.compile: STRING.}` /        — pragmas that add files / link options
  `{.passC: STRING.}` /            controlled by build-time strings
  `{.passL: STRING.}`

Any of these driven by a string the LLM constructed from environment
variables, build inputs, or user-controlled config is a build-time
RCE sink. LLM-emitted Nim frequently reaches for `staticExec("git " &
something)` to "embed the git sha at build" — that is almost always
the wrong tool. The safe forms:

* run the shell command in a separate build script, write the result to
  a generated `.nim` file, and `include` that;
* use `{.strdefine.}` / `{.intdefine.}` and pass values via `nim c -d:`;
* never concatenate untrusted text into `staticExec`.

What this flags
---------------
A bareword call to one of `staticExec`, `gorge`, `gorgeEx`,
`staticRead`, OR a `{.compile: ...}` / `{.passC: ...}` / `{.passL: ...}`
pragma.

Suppress an audited line with a trailing `# nim-static-ok` comment.

Out of scope (deliberately)
---------------------------
* `macros.staticExec` (same name, different module) — we treat any
  bareword `staticExec(` as the smell.
* Compile-time `readFile` inside a `static:` block is a related risk
  but not flagged here; this detector is single-purpose.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.nim, *.nims, *.nimble.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Bareword call to any of the dynamic-execution / dynamic-read builtins.
RE_STATIC_EXEC = re.compile(
    r"\b(staticExec|gorgeEx|gorge|staticRead)\s*\("
)

# Pragma forms: {.compile: "..."} / {.passC: "..."} / {.passL: "..."}
# We flag the pragma keyword itself; arg can be literal or expression.
RE_PRAGMA_BUILD = re.compile(
    r"\{\.\s*(compile|passC|passL)\s*:"
)

# Suppression marker: `# nim-static-ok` anywhere on the line.
RE_SUPPRESS = re.compile(r"#\s*nim-static-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `# ...` line comments and `"..."` / `\"\"\"...\"\"\"` /
    raw `r"..."` string-literal contents while keeping column positions
    stable. Triple-quoted strings are only collapsed when they open and
    close on the same line; otherwise the rest of the line is blanked.

    Nim has no `//` comments. `#[ ... ]#` block comments are best-effort
    handled when they open and close on the same line.
    """
    out: list[str] = []
    i = 0
    n = len(line)

    def emit_blank(k: int) -> None:
        out.append(" " * k)

    in_dq = False
    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""

        if not in_dq:
            # Single-line block comment #[ ... ]#
            if ch == "#" and nxt == "[":
                end = line.find("]#", i + 2)
                if end == -1:
                    emit_blank(n - i)
                    break
                emit_blank(end + 2 - i)
                i = end + 2
                continue
            # Line comment #  (but not pragma `{. ... .}`; pragmas use
            # braces, not `#`, so a bare `#` is always a comment).
            if ch == "#":
                emit_blank(n - i)
                break
            # Triple-quoted string """..."""
            if line.startswith('"""', i):
                end = line.find('"""', i + 3)
                if end == -1:
                    emit_blank(n - i)
                    break
                # Keep the opening quote so the column stays anchored,
                # blank the content, keep the closing quote.
                out.append('"""')
                emit_blank(end - (i + 3))
                out.append('"""')
                i = end + 3
                continue
            # Raw string r"..."
            if ch == "r" and nxt == '"':
                # Find unescaped closing " (raw strings have no escapes
                # inside; "" is an escaped quote in raw strings).
                j = i + 2
                while j < n:
                    if line[j] == '"':
                        if j + 1 < n and line[j + 1] == '"':
                            j += 2
                            continue
                        break
                    j += 1
                if j >= n:
                    emit_blank(n - i)
                    break
                out.append('r"')
                emit_blank(j - (i + 2))
                out.append('"')
                i = j + 1
                continue
            if ch == '"':
                in_dq = True
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue

        # Inside a normal "..." string.
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_dq = False
            out.append(ch)
            i += 1
            continue
        out.append(" ")
        i += 1

    return "".join(out)


def is_nim_file(path: Path) -> bool:
    return path.suffix in (".nim", ".nims", ".nimble")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        scrub = strip_comments_and_strings(raw)
        for m in RE_STATIC_EXEC.finditer(scrub):
            kind = "nim-" + m.group(1).lower()
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
        for m in RE_PRAGMA_BUILD.finditer(scrub):
            kind = "nim-pragma-" + m.group(1).lower()
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_nim_file(sub):
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

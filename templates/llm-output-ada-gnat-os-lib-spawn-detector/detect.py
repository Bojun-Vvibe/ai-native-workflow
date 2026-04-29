#!/usr/bin/env python3
"""Detect Ada `GNAT.OS_Lib.Spawn` and friends — process-launch sinks.

GNAT (the GNU Ada compiler) ships an `OS_Lib` package whose `Spawn`
family executes external programs:

    GNAT.OS_Lib.Spawn (Program_Name, Args, Success);
    Pid := GNAT.OS_Lib.Non_Blocking_Spawn (Cmd, Args);

There is also `System.OS_Lib` (the runtime mirror) and the
`Ada.Command_Line.Environment` + `Ada.Strings.Unbounded` patterns LLMs
sometimes glue together to call out. Whenever the program name or
argument list is built from user input rather than a vetted constant,
this is a classic command-injection sink.

What this flags
---------------
* `GNAT.OS_Lib.Spawn (...)`               — blocking spawn
* `GNAT.OS_Lib.Non_Blocking_Spawn (...)`  — async spawn
* `GNAT.OS_Lib.Spawn_With_Filter (...)`   — filtered spawn variant
* `System.OS_Lib.Spawn (...)`             — runtime mirror
* `OS_Lib.Spawn (...)`                    — `use`-shortened form
* Standalone `Spawn (...)` after `use GNAT.OS_Lib;` is too noisy
  to flag without false positives, so we require the `OS_Lib` prefix.

Suppression
-----------
Append `-- spawn-ok` to the line to silence a known-safe usage.

Out of scope (deliberately)
---------------------------
* `Ada.Directories.*` — file ops, not spawn.
* `Interfaces.C.Strings` glue without an explicit `Spawn` call.
* Custom binders into `system(3)` via `pragma Import`. Those need a
  separate detector keyed on the import name.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.adb`, `*.ads`, `*.ada`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"--\s*spawn-ok\b")

# `[GNAT|System|]OS_Lib.Spawn[_..]?` followed by optional whitespace
# and `(`. Case-insensitive: Ada is case-insensitive for identifiers.
RE_SPAWN_QUALIFIED = re.compile(
    r"\b(?:GNAT|System)\.OS_Lib\."
    r"(Spawn|Non_Blocking_Spawn|Spawn_With_Filter)\s*\(",
    re.IGNORECASE | re.DOTALL,
)
RE_SPAWN_USE_SHORT = re.compile(
    r"\bOS_Lib\."
    r"(Spawn|Non_Blocking_Spawn|Spawn_With_Filter)\s*\(",
    re.IGNORECASE | re.DOTALL,
)


def mask_ada_comments_and_strings(text: str) -> str:
    """Mask Ada `--` line comments and `"..."` string literals while
    preserving column positions and newlines.

    Ada has only line comments (`--` to end of line). String literals
    use `"..."` with the doubled-quote escape `""`. There is no block
    comment to worry about.
    """
    out = list(text)
    n = len(text)
    i = 0
    in_string = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_string:
            if ch == '"' and nxt == '"':
                # escaped quote inside string
                out[i] = " "
                out[i + 1] = " "
                i += 2
                continue
            if ch == '"':
                in_string = False
                i += 1
                continue
            out[i] = " " if ch != "\n" else "\n"
            i += 1
            continue
        # line comment
        if ch == "-" and nxt == "-":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        if ch == '"':
            in_string = True
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
    masked = mask_ada_comments_and_strings(text)
    raw_lines = text.splitlines()
    # Build line-start offset table for the masked text.
    line_starts = [0]
    for idx, ch in enumerate(masked):
        if ch == "\n":
            line_starts.append(idx + 1)

    def offset_to_linecol(off: int) -> tuple[int, int]:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, off - line_starts[lo] + 1

    seen: set[tuple[int, int]] = set()
    for m in RE_SPAWN_QUALIFIED.finditer(masked):
        line, col = offset_to_linecol(m.start())
        raw = raw_lines[line - 1] if line - 1 < len(raw_lines) else ""
        if RE_SUPPRESS.search(raw):
            continue
        seen.add((line, col))
        findings.append(
            (path, line, col, "ada-os-lib-spawn", raw.strip())
        )
    for m in RE_SPAWN_USE_SHORT.finditer(masked):
        # Avoid double-counting a fully-qualified hit: skip if the
        # char immediately before `OS_Lib.` is `.` (meaning it's the
        # tail of `GNAT.OS_Lib.` or `System.OS_Lib.`).
        start = m.start()
        prev_char = masked[start - 1] if start > 0 else ""
        if prev_char == ".":
            continue
        line, col = offset_to_linecol(start)
        raw = raw_lines[line - 1] if line - 1 < len(raw_lines) else ""
        if RE_SUPPRESS.search(raw):
            continue
        findings.append(
            (path, line, col, "ada-os-lib-spawn-use", raw.strip())
        )
    findings.sort(key=lambda t: (t[1], t[2]))
    return findings


def is_ada_file(path: Path) -> bool:
    return path.suffix.lower() in (".adb", ".ads", ".ada")


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_ada_file(sub):
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

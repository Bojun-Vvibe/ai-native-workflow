#!/usr/bin/env python3
"""Detect Octave / MATLAB `eval` / `evalin` / `feval` / `assignin`
invocations on dynamic strings.

In GNU Octave (and MATLAB), `eval(STR)` parses STR as Octave source and
runs it in the calling workspace; `evalin(WS, STR)` does the same in a
named workspace (`'base'` or `'caller'`); `feval(FN, ...)` calls a
function whose name is given by the string FN; `assignin(WS, NAME, V)`
writes a variable named by string NAME into a workspace. All four are
dynamic-code sinks: any caller-controlled fragment in the string
becomes runnable Octave code, with full filesystem and shell access.

LLM-emitted Octave/MATLAB code reaches for `eval` to "build a variable
name from a loop index" (e.g. `eval(['x' num2str(i) ' = 0'])`). The
safe replacement is almost always:

* a struct field (`x.(sprintf('f%d', i)) = 0`), or
* a cell array (`x{i} = 0`), or
* a function handle (`fn = @sin; fn(x)` instead of `feval('sin', x)`).

What this flags
---------------
A bareword `eval` / `evalin` / `feval` / `assignin` immediately
followed by `(` (function-call form). Comments (`%`, `#`) and string
literals (`'...'`, `"..."`) are masked first so the regex never
matches text inside them.

* `eval(cmd)`                       — UNSAFE
* `eval(['x = ' num2str(i)])`       — concat into eval, UNSAFE
* `evalin('base', s)`               — UNSAFE
* `feval(name, x, y)`               — string dispatch, UNSAFE
* `assignin('caller', vname, val)`  — dynamic assignment, UNSAFE

Out of scope (deliberately)
---------------------------
* `str2func`, `system`, `unix`, `dos`, `popen` — also dangerous but
  out of scope for this single-purpose detector.
* The two-argument form `eval(TRY, CATCH)` is still flagged — both
  arguments are code strings.

Suppression
-----------
A trailing `% eval-ok` (or `# eval-ok`) comment on the line suppresses
that line entirely.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for *.m files. Note: `.m` is also
used by Objective-C; this scanner additionally checks for Octave/MATLAB
markers (`function`, `endfunction`, `%`-comments, `1;` script header,
or no `#import`/`@interface` Objective-C tokens) before scanning a `.m`
file. Files with extension `.octave` are always scanned.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Bareword sink at function-call position.
RE_SINK = re.compile(
    r"(?<![A-Za-z0-9_.])(eval|evalin|feval|assignin)\s*\("
)

# Suppression marker.
RE_SUPPRESS = re.compile(r"[%#]\s*eval-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out `'...'` / `"..."` string contents and `%` / `#`
    line-comments while keeping column positions stable. Octave uses
    `%` and `#` as comment markers (both legal). Single-quote strings
    use doubled `''` for an embedded apostrophe; double-quote strings
    use `\\` escapes."""
    out: list[str] = []
    i = 0
    n = len(line)
    in_sq = False
    in_dq = False
    while i < n:
        ch = line[i]
        if in_sq:
            if ch == "'":
                if i + 1 < n and line[i + 1] == "'":
                    out.append("  ")
                    i += 2
                    continue
                in_sq = False
                out.append(ch)
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if in_dq:
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
            continue
        if ch == "%" or ch == "#":
            out.append(" " * (n - i))
            break
        if ch == '"':
            in_dq = True
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            # In Octave, `'` is also the transpose operator when it
            # follows an identifier, `)`, `]`, `}`, or `.`. Treat it
            # as transpose (not string) in that case.
            prev = out[-1] if out else ""
            if prev and (prev.isalnum() or prev in "_)]}."):
                out.append(ch)
                i += 1
                continue
            in_sq = True
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def looks_like_objc(text: str) -> bool:
    head = text[:4096]
    objc_tokens = ("#import", "@interface", "@implementation", "@protocol")
    return any(tok in head for tok in objc_tokens)


def is_octave_file(path: Path) -> bool:
    if path.suffix == ".octave":
        return True
    if path.suffix != ".m":
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if looks_like_objc(text):
        return False
    return True


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
        for m in RE_SINK.finditer(scrub):
            kind = "octave-" + m.group(1)
            findings.append((path, idx, m.start(1) + 1, kind, raw.strip()))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_octave_file(sub):
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

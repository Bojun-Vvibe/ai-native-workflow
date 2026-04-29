#!/usr/bin/env python3
"""Detect ChucK `Machine.add(...)` / `Machine.replace(...)` /
`Machine.spork(...)` runtime code-load sinks.

ChucK's `Machine` interface lets a running VM load and execute another
ChucK source file at runtime:

    Machine.add("evil.ck");
    Machine.add(userInput + ".ck");
    Machine.replace(currentShredID, dynamicPath);

This is the ChucK equivalent of `eval(load(filename))`: whenever the
argument is anything other than a manifest, audited string literal,
the program is loading code chosen at runtime from data that may be
attacker-controllable (config, network, user prompt, OSC message).

LLM-generated ChucK glue code reaches for `Machine.add` whenever the
model wants "dynamic patch loading" without knowing the safer
patterns (a static dispatch table, or vetting paths against an
allow-list before loading).

What this flags
---------------
* `Machine.add(expr)`        — primary code-load sink
* `Machine.replace(id, expr)` — same, but with shred id
* `Machine.spork(expr)`       — fork + load
* `Machine.eval(expr)`        — string-evaluation form

We flag whenever the call appears at expression position, regardless
of whether the argument looks like a literal: literal arguments are
also worth a manual review because they pin runtime behaviour to a
filesystem path the deployment may not control.

Suppression
-----------
Append `// machine-add-ok` to the line to silence a vetted call.

Usage
-----
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses into directories looking for `*.ck`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"//\s*machine-add-ok\b")

# Machine.<method>( with optional whitespace. We pin to a small set of
# methods that load or evaluate ChucK source at runtime.
RE_MACHINE_SINK = re.compile(
    r"(?:^|(?<=[\s;{}()=,!?:&|+\-*/<>]))"
    r"Machine\s*\.\s*(add|replace|spork|eval)\s*\("
)


def mask_chuck_comments_and_strings(text: str) -> str:
    """Replace comment and string-literal interiors with spaces while
    preserving column positions and newlines.

    ChucK lexical rules we cover:
      * `// line` comments
      * `/* block */` comments (non-nesting)
      * `"..."` strings with `\\` escapes
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " " if text[k] != "\n" else "\n"
            i = j
            continue
        if ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                j = n
            else:
                j += 2
            for k in range(i, j):
                out[k] = text[k] if text[k] == "\n" else " "
            i = j
            continue
        if ch == '"':
            k = i + 1
            while k < n:
                c = text[k]
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == '"' or c == "\n":
                    break
                k += 1
            end = k + 1 if k < n and text[k] == '"' else k
            for m in range(i + 1, max(i + 1, end - 1)):
                out[m] = text[m] if text[m] == "\n" else " "
            i = end
            continue
        i += 1
    return "".join(out)


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    masked = mask_chuck_comments_and_strings(text)
    raw_lines = text.splitlines()
    masked_lines = masked.splitlines()
    n = min(len(raw_lines), len(masked_lines))
    for idx in range(n):
        raw = raw_lines[idx]
        scrub = masked_lines[idx]
        if RE_SUPPRESS.search(raw):
            continue
        for m in RE_MACHINE_SINK.finditer(scrub):
            method = m.group(1)
            findings.append(
                (path, idx + 1, m.start() + 1,
                 f"chuck-machine-{method}", raw.strip())
            )
    return findings


def is_chuck_file(path: Path) -> bool:
    return path.suffix == ".ck"


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_chuck_file(sub):
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

#!/usr/bin/env python3
"""Detect F# (and surrounding .NET) dynamic-reflection invoke patterns.

The flagged shapes:

* `<expr>.Invoke(...)`         — `MethodInfo.Invoke`, `Delegate.Invoke`,
                                 etc. on a value obtained by reflection.
* `Type.GetMethod(<name>)`     — string-based method lookup, almost
                                 always followed by `.Invoke`.
* `Type.InvokeMember(<name>, ...)` — direct string-named member dispatch.
* `Activator.CreateInstance(<...>)` — string- / Type-based constructor
                                 dispatch (commonly paired with
                                 `Type.GetType(<string>)`).
* `Type.GetType(<string-literal-or-var>)` — runtime type lookup by name.
* `Assembly.Load(<...>)` / `Assembly.LoadFrom(<...>)` — loading an
                                 assembly chosen at runtime.

Why this matters for LLM-emitted F#:

The F# type system is genuinely powerful, and the idiomatic way to do
"dynamic dispatch" is a discriminated union or an interface. LLMs that
have seen a lot of C# reflection code will reach for `GetMethod(name)`
+ `Invoke(obj, args)` to "call a method by name", losing all type
safety AND opening up dispatch to arbitrary attacker-supplied names
when `name` is not a literal.

This is a heuristic, line-based scanner — the goal is to surface every
reflection invoke for human review, not to prove exploitability.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments_and_strings(line: str) -> str:
    """Blank out `// ...` and `(* ... *)` comments (single-line only) and
    `"..."`, `@"..."`, triple-quoted string literals while preserving
    column positions. Multi-line `(* ... *)` blocks are tracked by the
    file-level scanner.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    in_s: str | None = None  # None | '"' | '@"' | '"""'
    while i < n:
        ch = line[i]
        if in_s is None:
            # `// ...` line comment (F# uses `//`)
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                out.append(" " * (n - i))
                break
            # triple-quoted string `"""..."""`
            if ch == '"' and line[i : i + 3] == '"""':
                in_s = '"""'
                out.append('"""')
                i += 3
                continue
            # verbatim string `@"..."`
            if ch == "@" and i + 1 < n and line[i + 1] == '"':
                in_s = '@"'
                out.append('@"')
                i += 2
                continue
            if ch == '"':
                in_s = '"'
                out.append('"')
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside a string literal
        if in_s == '"""':
            if line[i : i + 3] == '"""':
                out.append('"""')
                in_s = None
                i += 3
                continue
            out.append(" ")
            i += 1
            continue
        if in_s == '@"':
            # verbatim string: `""` is an escaped quote, single `"` ends.
            if ch == '"' and i + 1 < n and line[i + 1] == '"':
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                out.append('"')
                in_s = None
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        # regular `"..."`
        if ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            out.append('"')
            in_s = None
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


# Each pattern is (kind, regex). The regex must use named or numbered
# groups for the column anchor; we use the start of the match.
PATTERNS: list[tuple[str, re.Pattern]] = [
    # `Type.GetMethod("...")` and friends; require the dot before to
    # avoid matching unrelated `GetMethod` words.
    ("get-method", re.compile(r"\.\s*GetMethod\s*\(")),
    ("get-property", re.compile(r"\.\s*GetProperty\s*\(")),
    ("get-field", re.compile(r"\.\s*GetField\s*\(")),
    ("invoke-member", re.compile(r"\.\s*InvokeMember\s*\(")),
    # `MethodInfo.Invoke(obj, args)` / `Delegate.DynamicInvoke(args)`.
    ("dynamic-invoke", re.compile(r"\.\s*DynamicInvoke\s*\(")),
    # Plain `.Invoke(` is noisy (event handlers, options); scope to
    # cases where it follows a likely-reflection token. We approximate
    # by requiring a preceding `MethodInfo`, `mi`, `method`, `m`, or a
    # closing paren of a `GetMethod(...)` call on the same line.
    (
        "method-invoke",
        re.compile(
            r"(?:MethodInfo|methodInfo|methodinfo|mi|method)\s*\.\s*Invoke\s*\("
        ),
    ),
    # Activator.CreateInstance(typeOrName, ...)
    ("activator-create", re.compile(r"\bActivator\s*\.\s*CreateInstance\s*\(")),
    # Type.GetType("Some.Name") — usually paired with Activator.
    ("type-get-type", re.compile(r"\bType\s*\.\s*GetType\s*\(")),
    # System.Type.GetType / System.Activator.CreateInstance qualified forms
    ("type-get-type", re.compile(r"\bSystem\.Type\s*\.\s*GetType\s*\(")),
    (
        "activator-create",
        re.compile(r"\bSystem\.Activator\s*\.\s*CreateInstance\s*\("),
    ),
    # Assembly.Load / Assembly.LoadFrom / Assembly.LoadFile
    (
        "assembly-load",
        re.compile(r"\bAssembly\s*\.\s*Load(?:From|File)?\s*\("),
    ),
]


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    in_block_comment = False
    seen_keys: set[tuple[int, int, str]] = set()

    for idx, raw_line in enumerate(raw.splitlines()):
        lineno = idx + 1
        line = raw_line

        # Best-effort multi-line `(* ... *)` block comment tracking.
        if in_block_comment:
            end = line.find("*)")
            if end == -1:
                continue
            line = " " * (end + 2) + line[end + 2 :]
            in_block_comment = False
        # Strip in-line `(* ... *)` (single-line) before further scanning.
        while True:
            s = line.find("(*")
            if s == -1:
                break
            e = line.find("*)", s + 2)
            if e == -1:
                # block continues on next line
                line = line[:s] + " " * (len(line) - s)
                in_block_comment = True
                break
            line = line[:s] + " " * (e + 2 - s) + line[e + 2 :]

        scrub = strip_comments_and_strings(line)

        for kind, pat in PATTERNS:
            for m in pat.finditer(scrub):
                key = (lineno, m.start() + 1, kind)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                findings.append(
                    (path, lineno, m.start() + 1, kind, raw_line.strip())
                )

    findings.sort(key=lambda t: (t[1], t[2]))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            files = (
                list(p.rglob("*.fs"))
                + list(p.rglob("*.fsx"))
                + list(p.rglob("*.fsi"))
            )
            for sub in sorted(files):
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

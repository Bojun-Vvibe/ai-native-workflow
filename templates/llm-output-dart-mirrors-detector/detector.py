#!/usr/bin/env python3
"""Detect risky `dart:mirrors` reflective invocation in Dart sources.

The `dart:mirrors` library exposes runtime reflection. Its `invoke`,
`invokeGetter`, `invokeSetter`, and `newInstance` methods take a
`Symbol` and a positional/named argument list, then dispatch to a
method or constructor whose name is decided at runtime. When that
`Symbol` (or the receiver) is derived from LLM output, network input,
or any user-controlled string, this is a code-execution sink: the
caller has handed an attacker the ability to pick which method runs.

In LLM-generated code we frequently see the anti-pattern

    final mirror = reflect(target);
    mirror.invoke(Symbol(userMethodName), [userArg]);

which is functionally `eval`. The defensive form is an explicit
allow-list dispatch (`switch` on a known set of names) without
mirrors at all -- which also lets the program tree-shake under AOT
compilation, where `dart:mirrors` is unavailable anyway.

What this flags
---------------
A call whose method name is one of:

    invoke, invokeGetter, invokeSetter, newInstance, apply

on a receiver chain that mentions `reflect(`, `reflectClass(`,
`reflectType(`, `currentMirrorSystem(`, or a variable whose
declaration involved one of those (best-effort, single-pass).

Also flags any `import 'dart:mirrors'` line at all, because the
package is widely considered a footgun and is not supported by the
production AOT toolchain.

Out of scope
------------
* `noSuchMethod` overrides (legitimate forwarding).
* `Function.apply` on a statically known function literal.
* Macros / build_runner / source_gen (compile-time, not runtime).

Suppression: append `// mirrors-ok` on the same line.

Usage
-----
    python3 detector.py <file_or_dir> [<file_or_dir> ...]

Recurses into directories looking for `*.dart`. Exit code 1 if any
findings, 0 otherwise. python3 stdlib only, single pass per line.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_IMPORT_MIRRORS = re.compile(
    r"""^\s*import\s+['"]dart:mirrors['"]"""
)

# Reflective entry-points that produce a *Mirror.
RE_REFLECT_ENTRY = re.compile(
    r"\b(?:reflect|reflectClass|reflectType|currentMirrorSystem)\s*\("
)

# Risky invocation methods. We require they appear after a `.` so we
# don't false-trip on a top-level function called `invoke` defined by
# user code.
RE_INVOKE_CALL = re.compile(
    r"\.(invoke|invokeGetter|invokeSetter|newInstance|apply)\s*\("
)

# Function.apply(fn, [args]) -- the global form.
RE_FUNCTION_APPLY = re.compile(r"\bFunction\s*\.\s*apply\s*\(")

RE_SUPPRESS = re.compile(r"//\s*mirrors-ok\b")


def strip_comments_and_strings(line: str) -> str:
    """Blank out string literals and `//` line comments while keeping
    column positions stable. Handles `'...'`, `"..."`, raw strings
    `r'...'` / `r"..."`, and escapes. Triple-quoted strings on a
    single line are also handled; multi-line triple strings are out
    of scope for this single-pass scanner (rare in LLM eval-injection
    patterns)."""
    out: list[str] = []
    i = 0
    n = len(line)
    quote: str | None = None
    triple = False
    while i < n:
        ch = line[i]
        if quote is None:
            # Line comment?
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                out.append(" " * (n - i))
                break
            # Raw string prefix `r'` or `r"`?
            if ch == "r" and i + 1 < n and line[i + 1] in ("'", '"'):
                out.append(" ")
                i += 1
                continue
            if ch in ("'", '"'):
                # Triple?
                if i + 2 < n and line[i + 1] == ch and line[i + 2] == ch:
                    quote = ch
                    triple = True
                    out.append("   ")
                    i += 3
                    continue
                quote = ch
                triple = False
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # inside string
        if not triple and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if triple and ch == quote and i + 2 < n and line[i + 1] == quote and line[i + 2] == quote:
            out.append("   ")
            quote = None
            triple = False
            i += 3
            continue
        if not triple and ch == quote:
            out.append(ch)
            quote = None
            i += 1
            continue
        out.append(" ")
        i += 1
    return "".join(out)


def is_dart_file(path: Path) -> bool:
    return path.suffix == ".dart"


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    saw_reflect = False
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        # Import check uses the raw line (we want to catch the literal).
        if RE_IMPORT_MIRRORS.search(raw):
            findings.append(
                (path, idx, 1, "dart-mirrors-import", raw.strip())
            )
        scrub = strip_comments_and_strings(raw)
        if RE_REFLECT_ENTRY.search(scrub):
            saw_reflect = True
        for m in RE_INVOKE_CALL.finditer(scrub):
            # Only flag .invoke/.newInstance/etc when the file actually
            # touched a reflective entry-point somewhere -- this keeps
            # the detector from screaming on unrelated `.apply(` chains
            # in iterable code.
            if not saw_reflect and m.group(1) == "apply":
                continue
            findings.append(
                (path, idx, m.start() + 1, f"dart-mirrors-{m.group(1)}", raw.strip())
            )
        for m in RE_FUNCTION_APPLY.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "dart-function-apply", raw.strip())
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_dart_file(sub):
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

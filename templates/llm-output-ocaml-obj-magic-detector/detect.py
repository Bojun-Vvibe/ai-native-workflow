#!/usr/bin/env python3
"""Detect OCaml `Obj.magic` (and friends) call sites.

`Obj.magic : 'a -> 'b` is OCaml's universal type cast. It bypasses
the type system entirely. There are a small number of legitimate
uses (heterogeneous containers, GADT-less existentials, FFI shims
with proven layout invariants) but in LLM-generated OCaml it almost
always shows up because the model wanted to "make the types line up"
without thinking through the algebra. The cost: undefined behavior,
segfaults, silent corruption.

Sibling escape hatches caught here:

- `Obj.repr`            (often paired with magic in unsafe round-trips)
- `Obj.obj`             (counterpart to repr)
- `Obj.field`           (raw block introspection)
- `Obj.set_field`       (raw block mutation)
- `Obj.unsafe_set_field`
- `Obj.unsafe_get`

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


UNSAFE_NAMES = (
    "magic",
    "repr",
    "obj",
    "field",
    "set_field",
    "unsafe_set_field",
    "unsafe_get",
)
RE_UNSAFE = re.compile(r"\bObj\.(" + "|".join(UNSAFE_NAMES) + r")\b")


def strip_comments_and_strings(
    text: str,
) -> str:
    """Blank out OCaml `(* ... *)` (nested) block comments and
    `"..."` string literals while preserving line/column positions.
    OCaml has no line comments. Returns the scrubbed text."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    block_depth = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if block_depth > 0:
            if ch == "*" and nxt == ")":
                out.append("  ")
                i += 2
                block_depth -= 1
                continue
            if ch == "(" and nxt == "*":
                out.append("  ")
                i += 2
                block_depth += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_str:
            if ch == "\\" and i + 1 < n:
                # preserve newlines in escape (rare) for column accuracy
                out.append("  " if text[i + 1] != "\n" else " \n")
                i += 2
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        # Not in string, not in block comment.
        if ch == "(" and nxt == "*":
            out.append("  ")
            i += 2
            block_depth = 1
            continue
        if ch == '"':
            out.append(ch)
            in_str = True
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def is_open_or_module_decl(line_scrub: str) -> bool:
    """Skip lines like `open Obj` or `module M = Obj` — they reference
    the module without invoking an unsafe primitive. Such lines do not
    contain `Obj.<name>` anyway, but be defensive."""
    s = line_scrub.lstrip()
    return s.startswith("open ") or s.startswith("module ")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrubbed = strip_comments_and_strings(raw)
    raw_lines = raw.splitlines()
    scrub_lines = scrubbed.splitlines()
    # pad scrub_lines to the same length as raw_lines (defensive)
    while len(scrub_lines) < len(raw_lines):
        scrub_lines.append("")
    for idx, scrub_line in enumerate(scrub_lines):
        lineno = idx + 1
        if is_open_or_module_decl(scrub_line):
            continue
        for m in RE_UNSAFE.finditer(scrub_line):
            name = m.group(1)
            findings.append(
                (
                    path,
                    lineno,
                    m.start() + 1,
                    f"obj-{name}",
                    raw_lines[idx].strip() if idx < len(raw_lines) else "",
                )
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(list(p.rglob("*.ml")) + list(p.rglob("*.mli"))):
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

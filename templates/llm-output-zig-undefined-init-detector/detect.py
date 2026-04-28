#!/usr/bin/env python3
"""Detect Zig declarations initialized with `undefined` where the type
is a scalar, pointer, optional, or error-union (i.e. cases where
read-before-write is almost certainly a bug).

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

In Zig, `= undefined` does not zero-initialize; it declares the bytes
to be genuinely uninitialized and reading before a definite write is
illegal behavior. The legitimate use is large stack buffers about to
be filled by a single OS call (`var buf: [N]u8 = undefined;`). The
dangerous shape — and the one LLMs emit to silence compile errors —
is scalar / pointer / optional / error-union variables initialized
to `undefined`.

This detector flags the dangerous shape and ignores array-typed
declarations.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ZIG_SUFFIXES = (".zig",)

SCALAR_TYPES = {
    "bool",
    "void",
    "noreturn",
    "anyopaque",
    "type",
    "f16",
    "f32",
    "f64",
    "f80",
    "f128",
    "usize",
    "isize",
    "comptime_int",
    "comptime_float",
    "c_char",
    "c_short",
    "c_ushort",
    "c_int",
    "c_uint",
    "c_long",
    "c_ulong",
    "c_longlong",
    "c_ulonglong",
    "c_longdouble",
}
# u0..u128, i0..i128 (we accept the full integer family by regex).
RE_INT_SCALAR = re.compile(r"^[ui](?:[0-9]|[1-9][0-9]{1,2})$")

# Match a top-level declaration form:
#   <var|const> <name>: <type> = undefined;
# We do not require the declaration to be at line start because Zig
# allows them inside blocks, but we anchor on the keyword token.
RE_DECL = re.compile(
    r"\b(var|const)\s+([A-Za-z_]\w*)\s*:\s*([^=;{}\n][^=;{\n]*?)\s*=\s*undefined\s*;"
)


def strip_comments_and_strings(text: str) -> str:
    """Blank out `//` line comments, `"..."` strings (with `\\` escapes),
    `\\\\` multi-line raw string lines, and `'.'` character literals,
    preserving line/column positions.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # `//` line comment to EOL (Zig has no block comments)
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # `\\` multiline string lines: each line starting with `\\` is a
        # raw string fragment. Blank from `\\` to EOL.
        if ch == "\\" and nxt == "\\":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # `"..."` string with `\` escapes
        if ch == '"':
            out.append('"')
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if c == '"':
                    out.append('"')
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        # `'c'` or `'\n'` character literal
        if ch == "'":
            out.append("'")
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if c == "'":
                    out.append("'")
                    i += 1
                    break
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def line_col_of(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl
    return line, col


def classify_type(type_str: str) -> str | None:
    """Return a category tag if the type is a 'dangerous-when-undefined'
    shape, else None.

    Categories: 'scalar', 'pointer', 'optional', 'error-union'.
    Array types (`[N]T`, `[_]T`) return None.
    """
    t = type_str.strip()
    if not t:
        return None
    # Array types: `[`...`]`T  (any bracketed length, including `[*]T`
    # which is a many-pointer — that we DO want to flag).
    # Distinguish `[*]` and `[*c]` (pointer-ish) from `[N]T` (array).
    if t.startswith("["):
        # Find the matching closing bracket of this prefix.
        depth = 0
        end = -1
        for idx, c in enumerate(t):
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = idx
                    break
        if end == -1:
            return None
        inner = t[1:end].strip()
        if inner in ("*", "*c"):
            return "pointer"
        # Otherwise it is an array length expression — do not flag.
        return None
    # Pointer prefixes
    if t.startswith("*"):
        return "pointer"
    # Optional pointer `?*` / `?[*]`
    if t.startswith("?*") or t.startswith("?[*"):
        return "pointer"
    # Optional anything else `?T`
    if t.startswith("?"):
        return "optional"
    # Error union: contains `!` not inside brackets / parens at top level.
    depth = 0
    for idx, c in enumerate(t):
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "!" and depth == 0:
            # error-union shape `E!T` or `!T`
            return "error-union"
    # Bare scalar?
    if t in SCALAR_TYPES:
        return "scalar"
    if RE_INT_SCALAR.match(t):
        return "scalar"
    return None


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrub = strip_comments_and_strings(raw)
    raw_lines = raw.splitlines()
    for m in RE_DECL.finditer(scrub):
        type_str = m.group(3)
        kind = classify_type(type_str)
        if kind is None:
            continue
        line, col = line_col_of(scrub, m.start())
        snippet = raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
        findings.append(
            (path, line, col, f"undefined-init-{kind}", snippet)
        )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix in ZIG_SUFFIXES:
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
            print(f"{f_path}:{line}:{col}: {kind} — {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

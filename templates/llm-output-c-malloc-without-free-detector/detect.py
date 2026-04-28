#!/usr/bin/env python3
"""Detect C heap allocations (malloc/calloc/realloc/strdup) that leak.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

Approach: extract top-level function bodies via brace matching after
stripping comments and string literals, then for each local pointer
assigned from an allocation function, check whether the body either
calls free(<ptr>), returns <ptr>, or stores <ptr> into *out / out->.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOC_FUNCS = ("malloc", "calloc", "realloc", "strdup", "strndup")
RE_ALLOC_ASSIGN = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*(?:\([^)]*\)\s*)?(" + "|".join(ALLOC_FUNCS) + r")\s*\("
)
RE_REALLOC_SELF = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*(?:\([^)]*\)\s*)?realloc\s*\(\s*\1\b"
)


def strip_comments_and_strings(text: str) -> str:
    """Remove /* */ and // comments and blank string literals so regex
    matching does not fire inside them. Preserves line numbers."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # block comment
        if ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                # unterminated — blank to end
                for c in text[i:]:
                    out.append("\n" if c == "\n" else " ")
                break
            for c in text[i : j + 2]:
                out.append("\n" if c == "\n" else " ")
            i = j + 2
            continue
        # line comment
        if ch == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                out.append(" " * (n - i))
                break
            out.append(" " * (j - i))
            i = j
            continue
        # string literal
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
        # char literal
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


def find_function_bodies(scrub: str):
    """Yield (body_text, body_start_offset) for each top-level function.

    Heuristic: find `<ident>(` where the matching `)` is followed by `{`
    at brace depth zero, then capture the matching `{...}` body.
    """
    n = len(scrub)
    depth = 0
    i = 0
    # Find brace-depth-zero positions of identifiers followed by `(`.
    sig_re = re.compile(r"\b[A-Za-z_]\w*\s*\(")
    while i < n:
        ch = scrub[i]
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0:
            m = sig_re.match(scrub, i)
            if m:
                # find matching `)`
                p = m.end() - 1  # position of `(`
                pdepth = 0
                j = p
                while j < n:
                    c = scrub[j]
                    if c == "(":
                        pdepth += 1
                    elif c == ")":
                        pdepth -= 1
                        if pdepth == 0:
                            break
                    j += 1
                if j >= n:
                    i = m.end()
                    continue
                # skip whitespace, then expect `{`
                k = j + 1
                while k < n and scrub[k] in " \t\r\n":
                    k += 1
                if k < n and scrub[k] == "{":
                    bdepth = 0
                    body_start = k
                    while k < n:
                        c = scrub[k]
                        if c == "{":
                            bdepth += 1
                        elif c == "}":
                            bdepth -= 1
                            if bdepth == 0:
                                yield scrub[body_start : k + 1], body_start
                                i = k + 1
                                break
                        k += 1
                    else:
                        i = n
                    continue
                i = m.end()
                continue
        i += 1


def line_col_of(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl
    return line, col


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrub = strip_comments_and_strings(raw)
    raw_lines = raw.splitlines()
    for body, body_off in find_function_bodies(scrub):
        # First check realloc-self (always a finding, irrespective of free).
        for m in RE_REALLOC_SELF.finditer(body):
            abs_off = body_off + m.start()
            line, col = line_col_of(scrub, abs_off)
            snippet = raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
            findings.append((path, line, col, "realloc-leak-on-fail", snippet))
        # Now leak detection per allocation assignment.
        for m in RE_ALLOC_ASSIGN.finditer(body):
            ptr = m.group(1)
            # disposed if any of: free(<ptr>); return <ptr>; *<x> = <ptr>;
            # <x>->y = <ptr>; <x>.y = <ptr>;
            disposed = False
            free_re = re.compile(r"\bfree\s*\(\s*" + re.escape(ptr) + r"\s*\)")
            return_re = re.compile(r"\breturn\s+" + re.escape(ptr) + r"\b")
            outptr_re = re.compile(
                r"(?:\*\s*[A-Za-z_]\w*|"
                r"[A-Za-z_]\w*\s*->\s*[A-Za-z_]\w*|"
                r"[A-Za-z_]\w*\s*\.\s*[A-Za-z_]\w*)"
                r"\s*=\s*" + re.escape(ptr) + r"\b"
            )
            if free_re.search(body) or return_re.search(body) or outptr_re.search(body):
                disposed = True
            if not disposed:
                abs_off = body_off + m.start()
                line, col = line_col_of(scrub, abs_off)
                snippet = (
                    raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
                )
                findings.append((path, line, col, "leak-no-free", snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix in (".c", ".h"):
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

#!/usr/bin/env python3
"""Detect Express/Koa/Fastify session cookies created without the
``Secure`` flag (or with ``secure: false``) outside of test fixtures.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SESSION_CALL_RE = re.compile(
    r"\b(?:session|cookieSession|expressSession|fastifySession\.register)\s*\(",
)
# Fastify-style: app.register(fastifySession, { ... }) or
# server.register(fastifySession, { ... }).
FASTIFY_REGISTER_RE = re.compile(r"\.register\s*\(\s*fastifySession\b")
COOKIE_BLOCK_RE = re.compile(r"\bcookie\s*:\s*\{")
SECURE_FALSE_RE = re.compile(r"\bsecure\s*:\s*false\b")
SECURE_ANY_RE = re.compile(r"\bsecure\s*:")
HTTPONLY_FALSE_RE = re.compile(r"\bhttpOnly\s*:\s*false\b")
SUPPRESS_RE = re.compile(r"//\s*llm-cookie-insecure-ok")

TEST_PATH_HINTS = ("/test/", "/tests/", "/__tests__/", ".spec.", ".test.")


def _is_test_path(path: Path) -> bool:
    s = str(path).replace("\\", "/")
    return any(h in s for h in TEST_PATH_HINTS)


def _find_matching_brace(source: str, open_pos: int) -> int:
    """Return index of the matching ``}`` for the ``{`` at ``open_pos``.

    Naive scan that tracks string literals (single, double, backtick)
    and line + block comments. Returns -1 if unmatched.
    """
    depth = 0
    i = open_pos
    n = len(source)
    in_str = None  # quote char or None
    in_line_comment = False
    in_block_comment = False
    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_str:
            if c == "\\":
                i += 1  # skip escaped char
            elif c == in_str:
                in_str = None
        else:
            if c == "/" and nxt == "/":
                in_line_comment = True
                i += 1
            elif c == "/" and nxt == "*":
                in_block_comment = True
                i += 1
            elif c in ("'", '"', "`"):
                in_str = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _line_of(source: str, pos: int) -> int:
    return source.count("\n", 0, pos) + 1


def scan(source: str, *, is_test: bool = False) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if is_test:
        return findings

    # Walk session-style calls and look for a `cookie: { ... }` literal
    # within the call's argument list.
    call_starts: List[int] = []
    for m in SESSION_CALL_RE.finditer(source):
        call_starts.append(m.end() - 1)  # position of '('
    for m in FASTIFY_REGISTER_RE.finditer(source):
        # Find the '(' belonging to .register(
        paren = source.find("(", m.start(), m.end())
        if paren != -1:
            call_starts.append(paren)
    call_starts.sort()

    for paren_open in call_starts:
        if source[paren_open] != "(":
            continue
        depth = 0
        i = paren_open
        n = len(source)
        end = -1
        in_str = None
        while i < n:
            c = source[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in ("'", '"', "`"):
                in_str = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        if end == -1:
            continue
        arg_region = source[paren_open:end]
        region_start = paren_open

        for cookie_match in COOKIE_BLOCK_RE.finditer(arg_region):
            brace_pos = region_start + cookie_match.end() - 1
            close = _find_matching_brace(source, brace_pos)
            if close == -1:
                continue
            block = source[brace_pos : close + 1]
            block_line = _line_of(source, brace_pos)

            # Suppression on the cookie line or the line just above.
            line_start = source.rfind("\n", 0, brace_pos) + 1
            line_end = source.find("\n", brace_pos)
            if line_end == -1:
                line_end = len(source)
            same_line = source[line_start:line_end]
            prev_line_end = line_start - 1
            prev_line_start = source.rfind("\n", 0, prev_line_end) + 1
            prev_line = source[prev_line_start:prev_line_end] if prev_line_end > 0 else ""
            if SUPPRESS_RE.search(same_line) or SUPPRESS_RE.search(prev_line):
                continue

            if SECURE_FALSE_RE.search(block):
                findings.append((
                    block_line,
                    "session cookie has secure: false — cookie will be sent over plain HTTP",
                ))
            elif not SECURE_ANY_RE.search(block):
                findings.append((
                    block_line,
                    "session cookie block has no `secure` key — Express defaults to insecure",
                ))

            if HTTPONLY_FALSE_RE.search(block):
                findings.append((
                    block_line,
                    "session cookie has httpOnly: false — cookie readable from document.cookie (XSS-exfiltratable)",
                ))

    # De-dup on (line, reason) while preserving order.
    seen = set()
    out: List[Tuple[int, str]] = []
    for fn in findings:
        if fn in seen:
            continue
        seen.add(fn)
        out.append(fn)
    return out


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.js", "*.mjs", "*.cjs", "*.ts"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source, is_test=_is_test_path(f))
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

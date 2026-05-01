#!/usr/bin/env python3
"""Detect Next.js getServerSideProps/getStaticProps/getInitialProps that
return process.env.<SECRET> in their props object.

Walks .js/.jsx/.ts/.tsx files. For each, locates declarations of the
three data-loading functions and scans their body (matched by brace
depth) for `props: { ... process.env.NAME ... }` where NAME looks like
a secret and is NOT prefixed `NEXT_PUBLIC_`.

Exit code:
  0 — no findings
  1 — at least one finding (or unreadable target)

Output format:
  <path>:<line>: nextjs-secret-in-props: <reason>

Suppression: append "// next-secret-ok" to the offending line.

Pure stdlib.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
MAX_BYTES = 2 * 1024 * 1024

SECRET_NAME_RE = re.compile(
    r"(?:SECRET|TOKEN|PASSWORD|PASS|PRIVATE|CREDENTIAL|DSN|WEBHOOK|"
    r"SIGNING|SALT|API_KEY|_KEY|^KEY_)",
    re.IGNORECASE,
)
NEXT_PUBLIC_PREFIX = "NEXT_PUBLIC_"

# Match a process.env.IDENT or process.env["IDENT"] reference.
ENV_REF_RE = re.compile(
    r"""process\.env\.([A-Za-z_][A-Za-z0-9_]*)|"""
    r"""process\.env\[\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s*\]"""
)

# Match a spread: ...process.env (full splat).
ENV_SPREAD_RE = re.compile(r"\.\.\.\s*process\.env\b")

# Function declaration patterns we care about.
FUNC_NAMES = ("getServerSideProps", "getStaticProps", "getInitialProps")
FUNC_DECL_RES = [
    # export async function getServerSideProps( ...
    re.compile(rf"\b(?:export\s+)?(?:async\s+)?function\s+{n}\s*[<(]")
    for n in FUNC_NAMES
] + [
    # export const getServerSideProps = async ( / : ... = async (
    re.compile(rf"\b(?:export\s+)?const\s+{n}\s*[:=]")
    for n in FUNC_NAMES
] + [
    # export const getServerSideProps: GetServerSideProps = async (
    # already covered by above; also the bare `getServerSideProps =`
    re.compile(rf"\b{n}\s*=\s*(?:async\s*)?\(")
    for n in FUNC_NAMES
]

SUPPRESS_RE = re.compile(r"//\s*next-secret-ok\b")


def _is_skippable(path: str) -> bool:
    base = os.path.basename(path)
    if base.startswith("."):
        return True
    _, ext = os.path.splitext(path)
    if ext.lower() not in EXTS:
        return True
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return True
    except OSError:
        return True
    return False


def _read_text(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\x00" in data[:1024]:
        return None
    return data.decode("utf-8", errors="replace")


def _find_function_bodies(text: str) -> List[Tuple[int, int]]:
    """Return list of (start_offset, end_offset) for each matched
    data-loading function body. The body spans from the `{` that opens
    the function body through its matching `}`.
    """
    bodies: List[Tuple[int, int]] = []
    seen_starts: set = set()
    for pat in FUNC_DECL_RES:
        for m in pat.finditer(text):
            decl_start = m.start()
            # Find the first `{` after the declaration that opens the
            # function body. We skip past parameter parens first.
            i = m.end()
            paren = 0
            n = len(text)
            # Walk to consume parameter list if present.
            while i < n:
                ch = text[i]
                if ch == "(":
                    paren += 1
                elif ch == ")":
                    paren -= 1
                    i += 1
                    if paren <= 0:
                        break
                    continue
                elif ch == "{" and paren == 0:
                    break
                i += 1
            # For arrow funcs we may have `=>` before `{`.
            while i < n and text[i] != "{":
                # Allow arrow form with implicit-return rejected (we
                # need a body; if we hit ; or end of statement, give up).
                if text[i] in ";\n" and "{" not in text[i:i + 200]:
                    break
                i += 1
            if i >= n or text[i] != "{":
                continue
            body_start = i
            if body_start in seen_starts:
                continue
            seen_starts.add(body_start)
            depth = 0
            j = body_start
            in_str = None  # type: ignore[assignment]
            while j < n:
                cj = text[j]
                if in_str:
                    if cj == "\\":
                        j += 2
                        continue
                    if cj == in_str:
                        in_str = None
                    j += 1
                    continue
                if cj in ("'", '"', "`"):
                    in_str = cj
                    j += 1
                    continue
                if cj == "{":
                    depth += 1
                elif cj == "}":
                    depth -= 1
                    if depth == 0:
                        bodies.append((body_start, j))
                        break
                j += 1
            del decl_start
    return bodies


def _offset_to_line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _scan_body(text: str, start: int, end: int) -> List[Tuple[int, str]]:
    """Within [start, end], find props-return leaks.

    Strategy: locate `props` keys (as object keys) and for each, find
    the value expression up to the matching `,` / `}` at the same
    brace depth, then scan that value for env references.
    """
    findings: List[Tuple[int, str]] = []
    body = text[start:end + 1]

    # Find every `props` object-key occurrence inside the body.
    # Pattern: word boundary, `props`, optional whitespace, `:`.
    for km in re.finditer(r"\bprops\s*:\s*", body):
        val_start = km.end()
        # The value should start with `{` (object literal) for the
        # leak shape; ignore others.
        # Skip whitespace.
        i = val_start
        while i < len(body) and body[i] in " \t\r\n":
            i += 1
        if i >= len(body) or body[i] != "{":
            continue
        # Find matching `}`.
        depth = 0
        j = i
        in_str = None  # type: ignore[assignment]
        while j < len(body):
            cj = body[j]
            if in_str:
                if cj == "\\":
                    j += 2
                    continue
                if cj == in_str:
                    in_str = None
                j += 1
                continue
            if cj in ("'", '"', "`"):
                in_str = cj
                j += 1
                continue
            if cj == "{":
                depth += 1
            elif cj == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(body):
            continue
        value_block = body[i:j + 1]
        block_offset = start + i

        # Spread of full process.env.
        for sm in ENV_SPREAD_RE.finditer(value_block):
            line_no = _offset_to_line(text, block_offset + sm.start())
            line_text = text.splitlines()[line_no - 1] if line_no - 1 < len(text.splitlines()) else ""
            if SUPPRESS_RE.search(line_text):
                continue
            findings.append(
                (line_no,
                 "props-spread-process-env (entire env splatted into props)")
            )

        # Individual env refs.
        for em in ENV_REF_RE.finditer(value_block):
            name = em.group(1) or em.group(2) or ""
            if not name:
                continue
            if name.startswith(NEXT_PUBLIC_PREFIX):
                continue
            if not SECRET_NAME_RE.search(name):
                continue
            line_no = _offset_to_line(text, block_offset + em.start())
            lines = text.splitlines()
            line_text = lines[line_no - 1] if line_no - 1 < len(lines) else ""
            if SUPPRESS_RE.search(line_text):
                continue
            findings.append(
                (line_no,
                 f"secret-env-in-props (process.env.{name})")
            )
    return findings


def _scan_file(path: str) -> List[Tuple[str, int, str]]:
    text = _read_text(path)
    if text is None:
        return []
    if not any(n in text for n in FUNC_NAMES):
        return []
    bodies = _find_function_bodies(text)
    findings: List[Tuple[str, int, str]] = []
    for start, end in bodies:
        for line_no, reason in _scan_body(text, start, end):
            findings.append((path, line_no, reason))
    # De-duplicate identical (path, line, reason).
    findings = sorted(set(findings))
    return findings


def _walk(target: str) -> Iterable[str]:
    if os.path.isfile(target):
        yield target
        return
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules",
                                                "__pycache__", ".next",
                                                ".venv", "venv", "dist",
                                                "build"}]
        for name in files:
            yield os.path.join(root, name)


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path>", file=sys.stderr)
        return 2
    target = argv[1]
    if not os.path.exists(target):
        print(f"{argv[0]}: no such path: {target}", file=sys.stderr)
        return 2

    findings: List[Tuple[str, int, str]] = []
    for path in _walk(target):
        if _is_skippable(path):
            continue
        findings.extend(_scan_file(path))

    findings.sort(key=lambda t: (t[0], t[1]))
    for path, line, reason in findings:
        print(f"{path}:{line}: nextjs-secret-in-props: {reason}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

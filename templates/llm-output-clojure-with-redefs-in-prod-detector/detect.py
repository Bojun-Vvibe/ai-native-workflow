#!/usr/bin/env python3
"""Detect Clojure `with-redefs` / `with-redefs-fn` usage in non-test code.

Usage:
    python3 detect.py <file_or_dir> [<file_or_dir> ...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.

`with-redefs` rebinds Var roots process-globally for the dynamic extent
of its body. It is appropriate in unit tests and dangerous in
production: other threads observe the rebinding mid-flight, and
exceptions on sibling threads can leave Vars permanently mutated.

LLMs frequently emit `with-redefs` to "swap an implementation" outside
test code because it is the shortest construct that achieves the goal
in REPL snippets. This detector flags every `with-redefs` /
`with-redefs-fn` form that lives outside files / namespaces that look
like test code.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CLJ_SUFFIXES = (".clj", ".cljs", ".cljc", ".cljx")

TEST_PATH_SEGMENTS = {"test", "tests", "spec", "specs", "it"}
TEST_FILENAME_SUFFIXES = (
    "_test.clj",
    "_test.cljs",
    "_test.cljc",
    "_test.cljx",
    "_spec.clj",
    "_spec.cljs",
    "_spec.cljc",
    "_spec.cljx",
)

RE_NS = re.compile(r"\(\s*ns\s+([A-Za-z0-9_.\-*+!?<>=/]+)")
# Match (with-redefs ...) or (with-redefs-fn ...) but not e.g.
# (with-redefs-foo ...) or (some.ns/with-redefs ...).
RE_WITH_REDEFS = re.compile(
    r"\(\s*(with-redefs(?:-fn)?)(?=[\s\[\(\)\]])"
)


def strip_comments_and_strings(text: str) -> str:
    """Blank out Clojure line comments (`;` to EOL) and string literals
    (`"..."` with `\\` escapes), preserving line/column positions.

    Also blanks `#_` form-level discard prefix so a discarded
    `with-redefs` form is not flagged. We only handle the simple case
    `#_(with-redefs ...)`: we replace `#_` and the matching opening
    parenthesis-balanced form with spaces.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # `;` line comment to EOL
        if ch == ";":
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
        # `\char` Clojure character literal (e.g. \space, \;) — skip
        # the backslash and the next char so a `\;` does not start a
        # comment.
        if ch == "\\" and i + 1 < n:
            out.append("\\")
            out.append(text[i + 1])
            i += 2
            continue
        # `#_` form discard: skip the `#_` and balance one form so a
        # discarded with-redefs is masked.
        if ch == "#" and nxt == "_":
            out.append("  ")
            i += 2
            # skip whitespace
            while i < n and text[i] in " \t\r\n":
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n and text[i] == "(":
                depth = 0
                while i < n:
                    c = text[i]
                    if c == "(":
                        depth += 1
                        out.append(" ")
                        i += 1
                    elif c == ")":
                        depth -= 1
                        out.append(" ")
                        i += 1
                        if depth == 0:
                            break
                    elif c == '"':
                        # mask balanced string inside the discarded form
                        out.append(" ")
                        i += 1
                        while i < n:
                            cc = text[i]
                            if cc == "\\" and i + 1 < n:
                                out.append("  ")
                                i += 2
                                continue
                            if cc == '"':
                                out.append(" ")
                                i += 1
                                break
                            out.append("\n" if cc == "\n" else " ")
                            i += 1
                    elif c == ";":
                        j = text.find("\n", i)
                        if j == -1:
                            out.append(" " * (n - i))
                            i = n
                        else:
                            out.append(" " * (j - i))
                            i = j
                    else:
                        out.append("\n" if c == "\n" else " ")
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


def looks_like_test_path(path: Path) -> bool:
    parts_lower = [p.lower() for p in path.parts]
    if any(seg in TEST_PATH_SEGMENTS for seg in parts_lower):
        return True
    name_lower = path.name.lower()
    if name_lower.endswith(TEST_FILENAME_SUFFIXES):
        return True
    return False


def looks_like_test_ns(scrubbed: str) -> bool:
    m = RE_NS.search(scrubbed)
    if not m:
        return False
    ns = m.group(1)
    if ns.endswith("-test") or ns.endswith(".test"):
        return True
    if ".test." in ns or "-test." in ns:
        return True
    return False


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    scrub = strip_comments_and_strings(raw)
    if looks_like_test_path(path) or looks_like_test_ns(scrub):
        return findings
    raw_lines = raw.splitlines()
    for m in RE_WITH_REDEFS.finditer(scrub):
        line, col = line_col_of(scrub, m.start())
        snippet = raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
        findings.append((path, line, col, "with-redefs-in-prod", snippet))
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix in CLJ_SUFFIXES:
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

#!/usr/bin/env python3
"""Detect `assert` used for runtime validation in production code.

Python's `assert` statement is removed by the bytecode compiler
when run with `-O` / `-OO` (or `PYTHONOPTIMIZE=1`). That is fine
for documenting invariants in test suites; it is **disastrous**
when the assertion is the only thing standing between a request
and an unauthorised action.

The classic shape:

    def withdraw(account, amount):
        assert account.owner == current_user(), "not authorised"
        assert amount <= account.balance, "overdraft"
        account.balance -= amount

Run that module under `python -O` and both checks vanish, so
*any* user can drain *any* account. CWE-617 ("Reachable
Assertion") and CPython's own docs both warn against this pattern,
yet LLMs emit it constantly because `assert` is shorter than
`if not ...: raise ValueError(...)`.

What this flags
---------------
* `assert <expr>` and `assert <expr>, <msg>` statements that
  appear inside a function body whose name does NOT start with
  `test_` and whose containing file is NOT obviously a test
  file (`test_*.py`, `*_test.py`, `tests/...`, `conftest.py`).
* Both the expression and the (optional) message are reported.

What this does NOT flag
-----------------------
* `assert` statements inside `def test_...` functions
* `assert` statements in files that look like test fixtures
  (path components: `tests/`, `test/`; filenames: `test_*.py`,
  `*_test.py`, `conftest.py`)
* Top-level / module-scope `assert` (these are typically
  type-narrowing hints for static analysers)
* Lines marked with a trailing `# assert-ok` comment
* Occurrences inside `#` comments or string literals

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files (and python shebang
files). Pure single-pass line scanner — does not import `ast` so
it stays robust against syntactically broken LLM snippets.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_DEF = re.compile(r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
RE_ASSERT = re.compile(r"^(?P<indent>\s*)assert\b(?P<rest>.*)$")
RE_SUPPRESS = re.compile(r"#\s*assert-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = in_triple
    while i < n:
        ch = line[i]
        if in_str is None:
            if ch == "#":
                out.append(" " * (n - i))
                break
            if ch in ("'", '"'):
                if line[i:i + 3] in ("'''", '"""'):
                    in_str = line[i:i + 3]
                    out.append(line[i:i + 3])
                    i += 3
                    continue
                in_str = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if len(in_str) == 1 and ch == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if line[i:i + len(in_str)] == in_str:
            out.append(in_str)
            i += len(in_str)
            in_str = None
            continue
        out.append(" ")
        i += 1
    if in_str is not None and len(in_str) == 1:
        in_str = None
    return "".join(out), in_str


def is_test_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if "tests" in parts or "test" in parts:
        return True
    name = path.name.lower()
    if name == "conftest.py":
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    return False


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    test_file = is_test_path(path)
    in_triple: str | None = None

    # Stack of (indent_width, is_test_function). When we see an
    # assert at indent > stack-top.indent, we are inside that
    # function. Pop entries whose indent is >= current line indent
    # before deciding.
    func_stack: list[tuple[int, bool]] = []

    for idx, raw in enumerate(text.splitlines(), start=1):
        # Skip pure-blank / comment-only lines for stack updates,
        # but still scan them for asserts (they will not match).
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        stripped = scrub.rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" \t"))

        # Pop any function frames we have exited.
        while func_stack and indent <= func_stack[-1][0]:
            func_stack.pop()

        # Function definition?
        m_def = RE_DEF.match(stripped)
        if m_def:
            def_indent = len(m_def.group("indent"))
            name = m_def.group("name")
            is_test_fn = name.startswith("test_") or name == "setUp" or name == "tearDown"
            func_stack.append((def_indent, is_test_fn or test_file))
            continue

        # Assert statement?
        m_a = RE_ASSERT.match(stripped)
        if not m_a:
            continue
        if RE_SUPPRESS.search(raw):
            continue
        # Must be inside a non-test function.
        if not func_stack:
            continue
        _, in_test = func_stack[-1]
        if in_test:
            continue
        col = (raw.find("assert")) + 1
        findings.append((path, idx, col, "assert-as-validation", raw.strip()))
    return findings


def is_python_file(path: Path) -> bool:
    if path.suffix == ".py":
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!") and "python" in first


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_python_file(sub):
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

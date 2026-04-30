#!/usr/bin/env python3
"""Detect insecure `tempfile.mktemp()` usage in Python source.

`tempfile.mktemp()` returns a path that does not yet exist; the
caller is then expected to create the file. Between the name
generation and the open, an attacker on the same filesystem can
race the call by creating a symlink or hard link at that path,
redirecting writes to a chosen location. Python's documentation
has carried a deprecation note for years; the safe primitives
are `tempfile.mkstemp()` (returns an already-open fd plus path)
and the higher-level context managers
`tempfile.NamedTemporaryFile`, `tempfile.TemporaryFile`,
`tempfile.SpooledTemporaryFile`, `tempfile.TemporaryDirectory`.

LLMs asked to "give me a temp file path" routinely emit
`tempfile.mktemp()` because the name reads as the obvious
counterpart to `mkdir`. This detector flags those calls so the
human reviewer can rewrite to `mkstemp` or a context manager.

What this flags
---------------
* `tempfile.mktemp(...)`     (with or without args)
* `from tempfile import mktemp` followed by a bare `mktemp(...)`
  call (including `from tempfile import mktemp as mk`)

What this does NOT flag
-----------------------
* `tempfile.mkstemp(...)`, `mkdtemp`, `NamedTemporaryFile`,
  `TemporaryFile`, `SpooledTemporaryFile`, `TemporaryDirectory`
* Lines marked with a trailing `# mktemp-ok` comment
* Occurrences inside `#` comments or string / docstring literals

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Negative lookahead so `mkstemp` / `mkdtemp` are not matched.
RE_TEMPFILE_MKTEMP = re.compile(
    r"\btempfile\s*\.\s*mktemp(?![A-Za-z_0-9])\s*\("
)
RE_FROM_IMPORT = re.compile(
    r"""^\s*from\s+tempfile\s+import\s+([^\n#]+)"""
)
RE_BARE_CALL = re.compile(r"\bmktemp(?![A-Za-z_0-9])\s*\(")

RE_SUPPRESS = re.compile(r"#\s*mktemp-ok\b")


def strip_comments_and_strings(line: str, in_triple: str | None = None) -> tuple[str, str | None]:
    """Mask out `#` comments and the *contents* of string literals
    (single + triple), preserving column positions. Triple-quote
    state is carried across lines."""
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


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    lines = text.splitlines()
    scrubbed: list[str] = []
    cursor: str | None = None
    for raw in lines:
        s, cursor = strip_comments_and_strings(raw, cursor)
        scrubbed.append(s)

    # Collect bare aliases for `mktemp` imported from tempfile.
    aliases: set[str] = set()
    for scrub in scrubbed:
        m = RE_FROM_IMPORT.match(scrub)
        if not m:
            continue
        names = m.group(1).replace("(", " ").replace(")", " ")
        for tok in names.split(","):
            tok = tok.strip()
            if not tok:
                continue
            parts = tok.split(" as ")
            base = parts[0].strip()
            alias = parts[1].strip() if len(parts) > 1 else base
            if base == "mktemp":
                aliases.add(alias)

    for idx, scrub in enumerate(scrubbed):
        raw = lines[idx]
        if RE_SUPPRESS.search(raw):
            continue

        for m in RE_TEMPFILE_MKTEMP.finditer(scrub):
            findings.append(
                (path, idx + 1, m.start() + 1, "tempfile-mktemp", raw.strip())
            )

        if aliases:
            for m in RE_BARE_CALL.finditer(scrub):
                start = m.start()
                # Skip `tempfile.mktemp(` matches already counted.
                if start > 0 and scrub[start - 1] == ".":
                    continue
                # Also skip if the alias used is not actually
                # imported (the regex matches the literal `mktemp`,
                # so for non-default aliases re-check).
                # The regex always captures the token "mktemp".
                # If the user did `import mktemp as mk`, the alias
                # in source will be `mk(...)` — handle below.
                findings.append(
                    (path, idx + 1, start + 1, "tempfile-mktemp-bare", raw.strip())
                )

            # Aliased calls: scan for any `<alias>(` token where
            # the alias is not literally `mktemp`.
            for alias in aliases:
                if alias == "mktemp":
                    continue
                pat = re.compile(r"\b" + re.escape(alias) + r"\s*\(")
                for m in pat.finditer(scrub):
                    start = m.start()
                    if start > 0 and scrub[start - 1] == ".":
                        continue
                    findings.append(
                        (path, idx + 1, start + 1, "tempfile-mktemp-aliased", raw.strip())
                    )

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

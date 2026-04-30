#!/usr/bin/env python3
"""Detect unsafe `zipfile.ZipFile(...).extractall(...)` ("Zip Slip") in
LLM-emitted Python.

`ZipFile.extractall()` happily writes any path encoded in the archive,
including absolute paths (`/etc/cron.d/evil`) and traversal sequences
(`../../etc/passwd`). An attacker who controls the archive can
overwrite arbitrary files on the host filesystem. This is the
"Zip Slip" class of bug (Snyk, 2018) and shows up almost any time an
LLM is asked "unzip this user upload".

CWE references
--------------
* **CWE-22**: Improper Limitation of a Pathname to a Restricted
  Directory ("Path Traversal").
* **CWE-23**: Relative Path Traversal.
* **CWE-73**: External Control of File Name or Path.

What this flags
---------------
* `ZipFile(...).extractall(...)` chained on one line.
* `zipfile.ZipFile(...).extractall(...)`.
* A bare `.extractall(` call when the same file imports `zipfile`
  (heuristic — flags the *call site*, not the import).
* `shutil.unpack_archive(<arg>)` (no `extract_dir`/no `format`
  hardening) — the stdlib wrapper has the same flaw.

What it does NOT flag
---------------------
* `extractall(...)` calls preceded on the same line, or anywhere in
  the same enclosing function body, by an explicit member-name
  validation against the destination — heuristically detected as a
  call to one of:
  - `os.path.realpath(...)` + `startswith(...)`
  - `Path(...).resolve()` + `is_relative_to(...)`
  - A function literally named `_safe_extract` / `safe_extract`
    (the canonical CPython advisory mitigation pattern).
* `extractall()` of a `tarfile` — see the sibling
  `llm-output-tarfile-extractall-traversal-detector` template.
* Lines suffixed with the suppression marker `# zipslip-ok`.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Recurses `*.py` under directories. Exit 1 if any findings,
0 otherwise. Pure python3 stdlib.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# zipslip-ok"

RE_IMPORT_ZIPFILE = re.compile(
    r"^\s*(?:import\s+zipfile|from\s+zipfile\s+import\b)"
)
RE_ZIPFILE_CALL = re.compile(r"\b(?:zipfile\s*\.\s*)?ZipFile\s*\(")
RE_EXTRACTALL = re.compile(r"\.extractall\s*\(")
RE_SHUTIL_UNPACK = re.compile(r"\bshutil\s*\.\s*unpack_archive\s*\(")

RE_SAFE_FUNC = re.compile(r"\b(?:_?safe_extract|_safe_unzip|safe_unzip)\s*\(")
RE_RESOLVE_GUARD = re.compile(r"\.resolve\s*\(\s*\).*\.is_relative_to\s*\(")
RE_REALPATH_GUARD = re.compile(r"realpath\s*\(.*\)\s*\.startswith\s*\(")


def _strip_strings_and_comment(line: str) -> str:
    out = []
    in_s = False
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < len(line):
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                in_s = False
                out.append(ch)
            else:
                out.append(" ")
        else:
            if ch == "#":
                break
            if ch in ("'", '"'):
                in_s = True
                quote = ch
                out.append(ch)
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _file_imports_zipfile(text: str) -> bool:
    for line in text.splitlines():
        if RE_IMPORT_ZIPFILE.match(line):
            return True
    return False


def _file_has_safe_helper(text: str) -> bool:
    for line in text.splitlines():
        cleaned = _strip_strings_and_comment(line)
        if RE_SAFE_FUNC.search(cleaned):
            return True
    return False


def _strip_triple_quoted_blocks(text: str) -> str:
    """Replace contents of triple-quoted string blocks with blank lines so
    docstrings / multi-line literals don't trigger pattern matches."""
    out_lines: list[str] = []
    in_block = False
    delim = ""
    for raw in text.splitlines():
        if not in_block:
            # Look for an opening triple quote that doesn't close on the
            # same line.
            for d in ('"""', "'''"):
                # Find first occurrence not preceded by a backslash.
                idx = raw.find(d)
                if idx == -1:
                    continue
                close = raw.find(d, idx + 3)
                if close == -1:
                    in_block = True
                    delim = d
                    out_lines.append(raw[: idx + 3])
                    break
            else:
                out_lines.append(raw)
                continue
            if not in_block:
                out_lines.append(raw)
        else:
            close = raw.find(delim)
            if close == -1:
                out_lines.append("")
            else:
                in_block = False
                out_lines.append(" " * close + delim + raw[close + 3 :])
                delim = ""
    return "\n".join(out_lines)


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    # Pre-strip triple-quoted blocks so we never match docstring contents,
    # but keep line numbers aligned with the original source.
    scrubbed = _strip_triple_quoted_blocks(text)
    scrubbed_lines = scrubbed.splitlines()
    raw_lines = text.splitlines()

    has_zipfile = _file_imports_zipfile(text)
    has_safe_helper = _file_has_safe_helper(text)

    for lineno, raw in enumerate(raw_lines, start=1):
        scrubbed_line = scrubbed_lines[lineno - 1] if lineno - 1 < len(scrubbed_lines) else raw
        if SUPPRESS in raw:
            continue
        line = _strip_strings_and_comment(scrubbed_line)

        # shutil.unpack_archive(...) — flag unconditionally.
        if RE_SHUTIL_UNPACK.search(line):
            findings.append(
                (path, lineno, "shutil-unpack-archive-traversal", raw.rstrip())
            )
            continue

        if not RE_EXTRACTALL.search(line):
            continue

        # Skip tarfile.* extractall calls — that's a separate detector.
        if re.search(r"\btarfile\b", line) or re.search(r"\bTarFile\b", line):
            continue

        # If the line itself constructs a ZipFile and chains extractall,
        # always flag.
        if RE_ZIPFILE_CALL.search(line):
            findings.append(
                (path, lineno, "zipfile-extractall-zip-slip", raw.rstrip())
            )
            continue

        # If a guard pattern is on this same line, skip.
        if RE_RESOLVE_GUARD.search(line) or RE_REALPATH_GUARD.search(line):
            continue

        # Otherwise, only flag bare `.extractall(` if the file imports
        # zipfile and does NOT define a safe-extract helper anywhere.
        if has_zipfile and not has_safe_helper:
            findings.append(
                (path, lineno, "zipfile-extractall-zip-slip", raw.rstrip())
            )

    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.py")):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

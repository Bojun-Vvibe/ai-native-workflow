#!/usr/bin/env python3
"""Detect unsafe tarfile / zipfile extraction calls.

Python's `tarfile.TarFile.extractall()` and `extract()` honour any
absolute paths or `..` segments embedded in member names, which
turns a hostile archive into an arbitrary-write primitive — the
"Zip Slip" / CVE-2007-4559 family. Python 3.12 added a `filter=`
parameter precisely so callers could opt into the safe `"data"`
filter; without it, the legacy fully-trusting behaviour is used
(and PEP 706 will eventually flip the default but is not there
yet on every supported runtime).

`zipfile.ZipFile.extractall()` / `.extract()` will *not* honour
`..` in member names on modern CPython, but they will still:
- silently truncate leading drive letters / leading slashes,
- happily traverse symlink members on Unix when the archive
  supplies them,
- write through any pre-existing symlinks in the destination tree.
So we still flag them — the recommendation is to validate member
names before extraction.

What this flags
---------------
* `tarfile.open(...).extractall(...)` style chained calls
* bare `.extractall(...)` on a name that looks like a tar/zip
  handle (`tar`, `tf`, `zf`, `zip_file`, `archive`, `tarball`)
* `tarfile.<TarFile>.extractall()` / `.extract()` without a
  `filter=` keyword (the only safe values are `"data"`,
  `"tar"`, or `tarfile.data_filter` / `tarfile.tar_filter`)
* `zipfile.ZipFile(...).extractall(...)` / `.extract(...)` —
  always flagged with kind `zip-extractall`
* `shutil.unpack_archive(...)` — always flagged

What this does NOT flag
-----------------------
* `tarfile`/`zipfile` calls with `filter="data"` /
  `filter="tar"` / `filter=tarfile.data_filter`
* Member iteration patterns (`for m in tar.getmembers(): ...`)
  that do their own path validation
* Lines marked with a trailing `# extractall-ok` comment
* Occurrences inside `#` comments or string literals

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.py` files (and python shebang
files).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# tar / zip handles — flag .extractall / .extract; we then
# disambiguate by receiver shape (zipfile.* / ZipFile / zf-style
# names => zip; everything else => tar with required safe filter).
RE_TAR_EXTRACT = re.compile(
    r"\b(?P<recv>"
    r"[A-Za-z_][A-Za-z0-9_]*"
    r"|tarfile\s*\.\s*open\s*\([^)]*\)"
    r"|zipfile\s*\.\s*ZipFile\s*\([^)]*\)"
    r")"
    r"\s*\.\s*(?P<meth>extractall|extract)\s*\("
)

RE_SHUTIL_UNPACK = re.compile(r"\bshutil\s*\.\s*unpack_archive\s*\(")

RE_SUPPRESS = re.compile(r"#\s*extractall-ok\b")

# Safe filter= values for tarfile.
RE_SAFE_FILTER = re.compile(
    r"filter\s*=\s*("
    r"['\"](?:data|tar)['\"]"
    r"|tarfile\s*\.\s*(?:data_filter|tar_filter)"
    r")"
)

# Heuristic names that suggest a tar handle vs a zip handle.
TAR_NAMES = {"tar", "tf", "tarball", "t", "archive", "tar_file"}
ZIP_NAMES = {"zf", "zip_file", "zipf", "zip", "z"}


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


def extract_call_args(scrubbed: str, paren_idx: int) -> str | None:
    depth = 0
    for j in range(paren_idx, len(scrubbed)):
        ch = scrubbed[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return scrubbed[paren_idx + 1:j]
    return None


def looks_like_zip(receiver: str) -> bool:
    base = receiver.strip().split(".")[0].split("(")[0]
    if "zipfile" in receiver or "ZipFile" in receiver:
        return True
    return base in ZIP_NAMES


def looks_like_tar(receiver: str) -> bool:
    base = receiver.strip().split(".")[0].split("(")[0]
    if "tarfile" in receiver or "TarFile" in receiver:
        return True
    return base in TAR_NAMES


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    in_triple: str | None = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        scrub, in_triple = strip_comments_and_strings(raw, in_triple)
        if RE_SUPPRESS.search(raw):
            continue

        # shutil.unpack_archive — always flagged.
        for m in RE_SHUTIL_UNPACK.finditer(scrub):
            findings.append(
                (path, idx, m.start() + 1, "shutil-unpack-archive", raw.strip())
            )

        # tar / zip extract — disambiguate by receiver heuristic.
        for m in RE_TAR_EXTRACT.finditer(scrub):
            recv = m.group("recv")
            meth = m.group("meth")
            # Decide tar vs zip by receiver shape; default to tar.
            if looks_like_zip(recv) and not looks_like_tar(recv):
                kind = f"zip-{meth}"
                findings.append((path, idx, m.start() + 1, kind, raw.strip()))
                continue
            # Tar path: skip if a safe filter is supplied. Check the
            # raw line because the scrubber blanks string contents
            # and would hide filter="data".
            if RE_SAFE_FILTER.search(raw):
                continue
            kind = f"tar-{meth}-no-safe-filter"
            findings.append((path, idx, m.start() + 1, kind, raw.strip()))
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

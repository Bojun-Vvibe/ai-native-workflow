#!/usr/bin/env python3
"""Detect Python imports that look hallucinated (not stdlib, not declared deps).

LLMs frequently emit `import foo` where `foo` is a plausible-but-nonexistent
package name (e.g., `import pandas_utils`, `import openai_helper`). This
detector parses Python source with `ast` and flags top-level imports whose
root module is neither in the Python standard library nor in an allowlist of
known third-party packages provided via `--known` (repeatable) or via a
`requirements.txt`-style file passed with `--known-file`.

Stdlib only. Does not import target code. Code-fence aware for Markdown.
Always exits 0.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import Iterable, Iterator, Tuple

# Conservative stdlib set covering CPython 3.8–3.13 top-level modules. We err
# on the side of inclusion to avoid false positives. (sys.stdlib_module_names
# only exists from 3.10+, so we ship a frozen list for portability.)
STDLIB = frozenset(
    """
    __future__ _thread abc aifc antigravity argparse array ast asynchat asyncio
    asyncore atexit audioop base64 bdb binascii binhex bisect builtins bz2
    cProfile calendar cgi cgitb chunk cmath cmd code codecs codeop collections
    colorsys compileall concurrent configparser contextlib contextvars copy
    copyreg crypt csv ctypes curses dataclasses datetime dbm decimal difflib
    dis distutils doctest email encodings ensurepip enum errno faulthandler
    fcntl filecmp fileinput fnmatch formatter fractions ftplib functools gc
    genericpath getopt getpass gettext glob graphlib grp gzip hashlib heapq
    hmac html http idlelib imaplib imghdr imp importlib inspect io ipaddress
    itertools json keyword lib2to3 linecache locale logging lzma mailbox
    mailcap marshal math mimetypes mmap modulefinder msilib msvcrt multiprocessing
    netrc nis nntplib ntpath numbers opcode operator optparse os ossaudiodev
    parser pathlib pdb pickle pickletools pipes pkgutil platform plistlib poplib
    posix posixpath pprint profile pstats pty pwd py_compile pyclbr pydoc
    pyexpat queue quopri random re readline reprlib resource rlcompleter runpy
    sched secrets select selectors shelve shlex shutil signal site smtpd smtplib
    sndhdr socket socketserver spwd sqlite3 sre_compile sre_constants sre_parse
    ssl stat statistics string stringprep struct subprocess sunau symbol symtable
    sys sysconfig syslog tabnanny tarfile telnetlib tempfile termios test textwrap
    threading time timeit tkinter token tokenize tomllib trace traceback
    tracemalloc tty turtle turtledemo types typing unicodedata unittest urllib
    uu uuid venv warnings wave weakref webbrowser winreg winsound wsgiref
    xdrlib xml xmlrpc zipapp zipfile zipimport zlib zoneinfo
    """.split()
)

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+\-]*)\s*$")
PYTHON_LANGS = {"python", "python3", "py"}


def _looks_like_markdown(path: str, text: str) -> bool:
    if path.lower().endswith((".md", ".markdown")):
        return True
    return bool(re.search(r"(?m)^\s*```", text))


def _extract_python_blocks(text: str, is_markdown: bool) -> Iterator[Tuple[int, str]]:
    """Yield (start_line, source_text) for python blocks (or whole file)."""
    if not is_markdown:
        yield 1, text
        return

    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_lang = ""
    buf: list[str] = []
    block_start = 0
    for i, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m and not in_fence:
            fence_char = m.group(1)[0]
            fence_len = len(m.group(1))
            fence_lang = m.group(2).lower()
            in_fence = True
            buf = []
            block_start = i + 1
            continue
        if in_fence and m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len and not m.group(2):
            if fence_lang in PYTHON_LANGS and buf:
                yield block_start, "\n".join(buf)
            in_fence = False
            fence_lang = ""
            buf = []
            continue
        if in_fence:
            buf.append(line)


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def _load_known(paths: Iterable[str]) -> set[str]:
    known: set[str] = set()
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    # requirements.txt-style: pkg, pkg==1.2, pkg[extra]>=1
                    m = re.match(r"[A-Za-z0-9_.\-]+", line)
                    if m:
                        known.add(_root_module(m.group(0).replace("-", "_").lower()))
        except OSError as e:
            print(f"{p}: ERROR loading known file: {e}", file=sys.stderr)
    return known


def _scan_block(
    path: str,
    block_start: int,
    source: str,
    known: set[str],
) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        line = block_start + (e.lineno or 1) - 1
        print(f"{path}:{line}: PYIMP000: could not parse python block: {e.msg}")
        return 0

    findings = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _root_module(alias.name).lower()
                if root in STDLIB or root in known:
                    continue
                line = block_start + (node.lineno - 1)
                print(
                    f"{path}:{line}: PYIMP001: import of unknown module "
                    f"'{alias.name}' (root '{root}' not stdlib, not in known set) "
                    f"| import {alias.name}"
                )
                findings += 1
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # relative import — skip; we cannot resolve package context here
                continue
            mod = node.module or ""
            root = _root_module(mod).lower()
            if not root or root in STDLIB or root in known:
                continue
            line = block_start + (node.lineno - 1)
            print(
                f"{path}:{line}: PYIMP002: from-import of unknown module "
                f"'{mod}' (root '{root}' not stdlib, not in known set) "
                f"| from {mod} import ..."
            )
            findings += 1
    return findings


def scan(path: str, text: str, known: set[str]) -> int:
    is_md = _looks_like_markdown(path, text)
    total = 0
    for block_start, source in _extract_python_blocks(text, is_md):
        total += _scan_block(path, block_start, source, known)
    print(f"# findings: {total}")
    return total


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def main(argv: list[str]) -> int:
    args = argv[1:]
    known: set[str] = set()
    known_files: list[str] = []
    paths: list[str] = []

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--known" and i + 1 < len(args):
            known.add(_root_module(args[i + 1].lower().replace("-", "_")))
            i += 2
        elif a == "--known-file" and i + 1 < len(args):
            known_files.append(args[i + 1])
            i += 2
        elif a in ("-h", "--help"):
            print(
                "usage: detector.py [--known PKG]... [--known-file REQ]... <path|->...",
                file=sys.stderr,
            )
            return 0
        else:
            paths.append(a)
            i += 1

    known |= _load_known(known_files)

    if not paths:
        print("usage: detector.py [--known PKG]... [--known-file REQ]... <path|->...", file=sys.stderr)
        print("# findings: 0")
        return 0

    for p in paths:
        display = p if p != "-" else "<stdin>"
        try:
            text = _read(p)
        except OSError as e:
            print(f"{display}: ERROR: {e}", file=sys.stderr)
            continue
        scan(display, text, known)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Detect tainted PHP filesystem-read calls vulnerable to CWE-22
(path traversal) / CWE-73 (external control of filename).

LLMs writing PHP under pressure to "just read the file" routinely
emit shapes like::

    $body = file_get_contents($_GET['path']);
    $body = file_get_contents("/var/data/" . $_POST['name']);
    readfile($_REQUEST['file']);
    $h = fopen($_GET['f'], 'r');
    $lines = file($_GET['log']);

All of these accept ``../../../etc/passwd`` or ``/etc/passwd``
without complaint. The single-arg ``file_get_contents`` form is also
SSRF-loaded because PHP's stream wrappers transparently fetch
``http://`` / ``ftp://`` / ``php://`` / ``data://`` / ``phar://``
URLs from the same call.

The safe shape is to resolve via ``realpath`` and verify the result
sits inside an explicit base directory before opening, e.g.::

    $base = realpath('/srv/data');
    $real = realpath($base . '/' . basename($name));
    if ($real === false || strncmp($real, $base . '/', strlen($base) + 1) !== 0) {
        http_response_code(400);
        exit;
    }
    $body = file_get_contents($real);

What this flags
---------------
Four kinds:

* ``php-file-get-contents-tainted`` — ``file_get_contents(<expr>)``
  where ``<expr>`` references a PHP superglobal
  (``$_GET`` / ``$_POST`` / ``$_REQUEST`` / ``$_COOKIE`` /
  ``$_FILES`` / ``$_SERVER``) or contains ``.`` string concatenation
  with one.
* ``php-readfile-tainted`` — ``readfile(<expr>)`` with the same
  condition.
* ``php-fopen-tainted`` — ``fopen(<expr>, ...)`` with the same
  condition.
* ``php-file-tainted`` — ``file(<expr>)`` (line-array reader) with
  the same condition.

What this does NOT flag
-----------------------
* Fully literal paths, e.g. ``file_get_contents('/etc/hostname')``
  or ``readfile(__DIR__ . '/static/banner.txt')``.
* Reads where the variable was clearly produced by ``realpath(...)``
  on the same line (``$p = realpath(...); file_get_contents($p)``
  is two lines and we only look at the call line itself, but we do
  recognise inline ``file_get_contents(realpath($x))``).
* Lines suffixed with ``// llm-allow:php-path-traversal`` or
  ``# llm-allow:php-path-traversal``.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Scans ``.php``, ``.phtml``, ``.inc``, ``.md``, ``.markdown``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:php-path-traversal"

SCAN_SUFFIXES = (".php", ".phtml", ".inc", ".md", ".markdown")

# ---------------------------------------------------------------------------
# Markdown fence extraction. Inside ``.md`` we only scan ```php / ```phtml
# fenced blocks.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_PHP_LANGS = {"php", "phtml", "php5", "php7", "php8"}


def _iter_php_blocks(text: str):
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _PHP_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Per-line lexer: replace string-literal contents with spaces so that
# superglobal references inside a literal don't cause false positives,
# and drop ``//`` and ``#`` line comments.
# ---------------------------------------------------------------------------

def _strip_strings_and_comments(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False  # single-quoted
    in_d = False  # double-quoted
    while i < n:
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_s = False
                out.append("'")
            else:
                out.append(" ")
        elif in_d:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_d = False
                out.append('"')
            else:
                out.append(" ")
        else:
            # Line-comment starters in PHP: // and #
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == "#":
                break
            if ch == "'":
                in_s = True
                out.append("'")
            elif ch == '"':
                in_d = True
                out.append('"')
            else:
                out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Argument extraction: given the content of ``line`` and the index of
# the opening ``(`` of the call, return the substring covering the
# first argument (up to the matching ``,`` at depth 0 or the matching
# ``)``). Operates on the comment-stripped line so depth tracking is
# safe.
# ---------------------------------------------------------------------------

def _first_arg(line: str, open_paren: int) -> str | None:
    depth = 0
    start = open_paren + 1
    i = start
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return line[start:i]
            depth -= 1
        elif ch == "," and depth == 0:
            return line[start:i]
        i += 1
    # Unterminated on this line — return what we have. Better to
    # over-flag than silently miss split-line calls.
    return line[start:] if start < n else None


SUPERGLOBAL_RE = re.compile(
    r"\$_(?:GET|POST|REQUEST|COOKIE|FILES|SERVER|ENV)\b"
)
USER_INPUT_HELPER_RE = re.compile(
    r"\b(?:filter_input|getenv|apache_request_headers|stream_get_contents)\s*\("
)
REALPATH_INLINE_RE = re.compile(r"\brealpath\s*\(")


def _is_tainted_arg(arg: str) -> bool:
    """True if the argument expression appears to carry user input."""
    if arg is None:
        return False
    a = arg.strip()
    if not a:
        return False
    # Allow inline realpath()-wrapped expressions; if the whole arg is
    # realpath(...) we treat it as audited.
    if a.startswith("realpath(") and a.endswith(")"):
        # but only if there's no superglobal *outside* the realpath
        # (which we can't easily tell here). Conservative: trust it.
        return False
    if SUPERGLOBAL_RE.search(a):
        return True
    if USER_INPUT_HELPER_RE.search(a):
        return True
    return False


# Call shapes we look for. Anchored on the function name so that
# ``MyClass::file_get_contents`` (a method on a user class) doesn't
# trigger.
CALL_SHAPES = (
    ("php-file-get-contents-tainted",
     re.compile(r"(?<![A-Za-z0-9_>:\\])file_get_contents\s*\(")),
    ("php-readfile-tainted",
     re.compile(r"(?<![A-Za-z0-9_>:\\])readfile\s*\(")),
    ("php-fopen-tainted",
     re.compile(r"(?<![A-Za-z0-9_>:\\])fopen\s*\(")),
    ("php-file-tainted",
     re.compile(r"(?<![A-Za-z0-9_>:\\])file\s*\(")),
)


def _scan_block(block: str, base_lineno: int) -> list[tuple[int, str, str]]:
    """Return (1-indexed line number relative to base_lineno+1, kind, raw line)."""
    findings: list[tuple[int, str, str]] = []
    for offset, raw in enumerate(block.splitlines(), start=1):
        if SUPPRESS in raw:
            continue
        scrubbed = _strip_strings_and_comments(raw)
        for kind, regex in CALL_SHAPES:
            for m in regex.finditer(scrubbed):
                # Locate the ``(`` we matched.
                paren = scrubbed.find("(", m.start())
                if paren < 0:
                    continue
                arg = _first_arg(scrubbed, paren)
                if _is_tainted_arg(arg or ""):
                    lineno = base_lineno + offset
                    findings.append((lineno, kind, raw.rstrip()))
                    break  # one finding per line is enough
    return findings


# ---------------------------------------------------------------------------
# File / directory walker.
# ---------------------------------------------------------------------------

def _iter_files(roots: list[str]):
    for root in roots:
        p = Path(root)
        if p.is_file():
            yield p
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() in SCAN_SUFFIXES:
                    yield child


def _scan_path(path: Path) -> list[tuple[int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[tuple[int, str, str]] = []
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        for body, line_offset in _iter_php_blocks(text):
            findings.extend(_scan_block(body, line_offset))
    else:
        findings.extend(_scan_block(text, 0))
    return findings


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    any_finding = False
    for path in _iter_files(argv):
        for lineno, kind, raw in _scan_path(path):
            print(f"{path}:{lineno}: {kind}: {raw.strip()}")
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

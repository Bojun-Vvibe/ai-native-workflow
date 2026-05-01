#!/usr/bin/env python3
"""Detect Ruby SSRF / file-read / pipe-injection footguns produced by
LLM output: tainted ``open`` / ``URI.open`` / ``Net::HTTP.get(URI(...))``
calls where the argument is not a fixed string literal beginning with
``http://`` or ``https://``.

Background
----------

Ruby's ``Kernel#open`` (with ``require 'open-uri'``) is a triple-loaded
foot-gun: a string ``"http://..."`` becomes an HTTP fetch, a string
``"/etc/passwd"`` becomes a local file read, and (pre-Ruby 3.0) a
string ``"|whoami"`` becomes a piped subprocess.

A LLM under pressure to "just make the request" will write::

    body = open(params[:url]).read
    body = URI.open(params[:url]).read
    body = Net::HTTP.get(URI(params[:url]))

All three are CWE-918 SSRF (and the first is also CWE-22 / CWE-78).

The detector flags four kinds (see README for definitions):
``ruby-kernel-open-tainted``, ``ruby-uri-open-tainted``,
``ruby-openuri-require``, ``ruby-net-http-get-uri-tainted``.

Suppress with ``# llm-allow:ruby-ssrf`` on the same source line.

Stdlib only. Exit code 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# llm-allow:ruby-ssrf"

SCAN_SUFFIXES = (".rb", ".rake", ".ru", ".md", ".markdown")


# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_RUBY_LANGS = {"rb", "ruby"}


def _iter_ruby_blocks(text: str):
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _RUBY_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Comment masking. Ruby comments start with ``#`` (not inside strings)
# and run to EOL. We mask comments before applying shape regexes so
# example snippets in comments don't trigger.
# ---------------------------------------------------------------------------

def _mask_comments(line: str) -> str:
    # Naive but effective: find first ``#`` not inside a single/double
    # quoted string. Good enough for the shapes we care about.
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            i += 2
            continue
        if not in_s and ch == '"':
            in_d = not in_d
        elif not in_d and ch == "'":
            in_s = not in_s
        elif not in_s and not in_d and ch == "#":
            return line[:i] + " " * (len(line) - i)
        i += 1
    return line


# ---------------------------------------------------------------------------
# "Safe literal" recogniser. A string literal that begins with
# http:// or https:// is treated as a fixed fetch target -> not flagged.
# ---------------------------------------------------------------------------

_SAFE_URL_RE = re.compile(r"""^\s*(['"])https?://""")


def _arg_is_safe_literal(arg: str) -> bool:
    arg = arg.strip()
    return bool(_SAFE_URL_RE.match(arg))


# ---------------------------------------------------------------------------
# Argument extractor: given a source line and the index of the ``(`` after
# a call name, return the substring inside the matched parens (top-level)
# or None if unbalanced.
# ---------------------------------------------------------------------------

def _extract_paren_arg(s: str, lparen_idx: int) -> str | None:
    depth = 0
    in_s = False
    in_d = False
    i = lparen_idx
    start = lparen_idx + 1
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            i += 2
            continue
        if not in_s and ch == '"':
            in_d = not in_d
        elif not in_d and ch == "'":
            in_s = not in_s
        elif not in_s and not in_d:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return s[start:i]
        i += 1
    return None


# ---------------------------------------------------------------------------
# Shape 1: bare ``open(...)`` or ``Kernel.open(...)`` with non-literal arg.
#
# We only flag when the argument is not a safe http(s):// literal. We
# do not flag ``File.open`` or ``IO.open`` (those don't go through the
# open-uri kernel hijack).
# ---------------------------------------------------------------------------

_KERNEL_OPEN_RE = re.compile(
    r"(?<![\w.:])(?:Kernel\s*\.\s*)?open\s*\("
)


def _scan_kernel_open(line: str):
    for m in _KERNEL_OPEN_RE.finditer(line):
        # Reject if preceded by File. / IO. / Tempfile. / Net::HTTP. etc.
        prefix = line[max(0, m.start() - 16):m.start()]
        if re.search(r"(?:File|IO|Tempfile|StringIO|Zlib|Pathname|Dir|Net::HTTP|Net::FTP|Net::SMTP|Net::POP3|Net::IMAP|URI)\s*\.\s*$", prefix):
            continue
        if re.search(r"def\s+$", prefix):
            continue
        lparen = m.end() - 1
        arg = _extract_paren_arg(line, lparen)
        if arg is None:
            # Probably multi-line; flag conservatively only if there's
            # no safe-looking literal at the start.
            tail = line[m.end():]
            if _arg_is_safe_literal(tail):
                continue
            yield ("ruby-kernel-open-tainted", m.start())
            continue
        if _arg_is_safe_literal(arg):
            continue
        yield ("ruby-kernel-open-tainted", m.start())


# ---------------------------------------------------------------------------
# Shape 2: ``URI.open(expr)`` or ``URI(expr).open`` with non-literal arg.
# ---------------------------------------------------------------------------

_URI_OPEN_RE = re.compile(r"(?<![\w:])URI\s*\.\s*open\s*\(")
_URI_CALL_OPEN_RE = re.compile(r"(?<![\w:])URI\s*\(")


def _scan_uri_open(line: str):
    for m in _URI_OPEN_RE.finditer(line):
        lparen = m.end() - 1
        arg = _extract_paren_arg(line, lparen)
        if arg is not None and _arg_is_safe_literal(arg):
            continue
        yield ("ruby-uri-open-tainted", m.start())
    for m in _URI_CALL_OPEN_RE.finditer(line):
        lparen = m.end() - 1
        arg = _extract_paren_arg(line, lparen)
        if arg is None:
            continue
        # Must be followed by .open or .read-via-open chain to count.
        tail = line[m.start() + (m.end() - m.start()) + len(arg) + 1:]
        if not re.match(r"\s*\.\s*open\b", tail):
            continue
        if _arg_is_safe_literal(arg):
            continue
        yield ("ruby-uri-open-tainted", m.start())


# ---------------------------------------------------------------------------
# Shape 3: file-level ``require 'open-uri'`` combined with ANY later
# ``open(...)`` call. Reported once per file.
# ---------------------------------------------------------------------------

_REQUIRE_OPENURI_RE = re.compile(r"^\s*require\s+['\"]open-uri['\"]")


# ---------------------------------------------------------------------------
# Shape 4: ``Net::HTTP.get(URI(expr))`` / ``Net::HTTP.get_response(URI(expr))``
# / ``Net::HTTP.start(host_expr, ...)`` with non-literal expr.
# ---------------------------------------------------------------------------

_NET_HTTP_GET_RE = re.compile(
    r"(?<![\w:])Net\s*::\s*HTTP\s*\.\s*(get|get_response|post|post_form)\s*\("
)
_NET_HTTP_START_RE = re.compile(
    r"(?<![\w:])Net\s*::\s*HTTP\s*\.\s*start\s*\("
)


def _scan_net_http(line: str):
    for m in _NET_HTTP_GET_RE.finditer(line):
        lparen = m.end() - 1
        arg = _extract_paren_arg(line, lparen)
        if arg is None:
            continue
        # The arg is typically ``URI(expr)`` or ``URI.parse(expr)`` or
        # a string. Drill in.
        inner = arg.strip()
        m2 = re.match(r"URI\s*(?:\.\s*parse\s*)?\(", inner)
        if m2:
            inner_arg = _extract_paren_arg(inner, m2.end() - 1)
            if inner_arg is not None and _arg_is_safe_literal(inner_arg):
                continue
            yield ("ruby-net-http-get-uri-tainted", m.start())
            continue
        if _arg_is_safe_literal(inner):
            continue
        yield ("ruby-net-http-get-uri-tainted", m.start())
    for m in _NET_HTTP_START_RE.finditer(line):
        lparen = m.end() - 1
        arg = _extract_paren_arg(line, lparen)
        if arg is None:
            continue
        # First positional arg is the host. If it's a literal string,
        # safe; otherwise tainted.
        first = arg.split(",", 1)[0]
        if _arg_is_safe_literal(first):
            continue
        # Skip if first arg is the literal host string with quotes.
        if re.match(r"\s*['\"][\w.\-]+['\"]\s*$", first):
            continue
        yield ("ruby-net-http-get-uri-tainted", m.start())


# ---------------------------------------------------------------------------
# File scanner.
# ---------------------------------------------------------------------------

def _scan_text(text: str, start_line: int = 0):
    """Yield (line_no_1based, kind) findings."""
    saw_openuri = False
    saw_open_call = False
    open_call_first_line = None
    for idx, raw in enumerate(text.splitlines()):
        line_no = start_line + idx + 1
        if SUPPRESS in raw:
            continue
        if _REQUIRE_OPENURI_RE.match(raw):
            saw_openuri = True
            continue
        masked = _mask_comments(raw)
        for kind, _col in _scan_kernel_open(masked):
            yield (line_no, kind)
            if not saw_open_call:
                saw_open_call = True
                open_call_first_line = line_no
        for kind, _col in _scan_uri_open(masked):
            yield (line_no, kind)
        for kind, _col in _scan_net_http(masked):
            yield (line_no, kind)
    if saw_openuri and saw_open_call and open_call_first_line is not None:
        yield (open_call_first_line, "ruby-openuri-require")


def scan_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"{path}: error: {exc}", file=sys.stderr)
        return []
    findings = []
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        for body, line_offset in _iter_ruby_blocks(text):
            for line_no, kind in _scan_text(body, start_line=line_offset):
                findings.append((line_no, kind))
    else:
        for line_no, kind in _scan_text(text):
            findings.append((line_no, kind))
    return findings


def _iter_paths(roots):
    for root in roots:
        p = Path(root)
        if p.is_file():
            yield p
        elif p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SCAN_SUFFIXES:
                    yield sub


def main(argv):
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    any_findings = False
    for path in _iter_paths(argv[1:]):
        for line_no, kind in scan_file(path):
            print(f"{path}:{line_no}: {kind}: ruby SSRF / open-uri tainted shape")
            any_findings = True
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

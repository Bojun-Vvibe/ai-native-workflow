#!/usr/bin/env python3
"""Detect Kotlin / OkHttp anti-patterns that disable TLS certificate or
hostname verification.

LLMs love to "fix" SSL handshake errors by handing OkHttp a trust-all
``X509TrustManager`` and a permissive ``HostnameVerifier``. The
resulting client accepts any peer certificate, which is a textbook
CWE-295 (Improper Certificate Validation) defect.

Three shapes are flagged:

1. **trustall-trust-manager** — an ``X509TrustManager`` (or
   ``X509ExtendedTrustManager``) whose ``checkServerTrusted`` /
   ``checkClientTrusted`` body is empty, ``return``, contains only a
   comment, or whose ``getAcceptedIssuers`` returns ``emptyArray()``,
   ``arrayOf()``, or ``null``.
2. **trustall-hostname-verifier** — a ``HostnameVerifier`` whose
   ``verify`` implementation always returns ``true``, **or** the
   builder pattern ``.hostnameVerifier { _, _ -> true }`` /
   ``.hostnameVerifier(HostnameVerifier { _, _ -> true })``.
3. **trustall-okhttp-builder** — an ``OkHttpClient.Builder()`` chain
   that calls ``.sslSocketFactory(...)`` together with one of the
   above shapes, or that hooks up an SSLContext built with the
   trust-all manager (``SSLContext.getInstance("...").init(null,
   trustAllCerts, ...)``).

A finding is suppressed if the same logical line carries
``// llm-allow:trustall-tls``. String literal interiors and comment
bodies are masked before pattern matching, so docstring examples don't
fire.

Fenced ``kt`` / ``kotlin`` code blocks are extracted from Markdown.

Stdlib only. Exit code 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// llm-allow:trustall-tls"

SCAN_SUFFIXES = (".kt", ".kts", ".md", ".markdown")


# ---------------------------------------------------------------------------
# Masking: blank string literal contents and comment bodies, preserving
# newlines and delimiters so line numbers stay stable.
# ---------------------------------------------------------------------------


def _strip_strings_and_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    in_line_c = False
    in_block_c = 0  # depth (Kotlin allows nested /* */)
    in_str = False
    in_triple = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_c:
            if c == "\n":
                in_line_c = False
                out.append(c)
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_c:
            if c == "/" and nxt == "*":
                in_block_c += 1
                out.append("  ")
                i += 2
                continue
            if c == "*" and nxt == "/":
                in_block_c -= 1
                out.append("  ")
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if in_triple:
            if c == '"' and text[i:i + 3] == '"""':
                out.append('"""')
                in_triple = False
                i += 3
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if in_str:
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == '"':
                out.append('"')
                in_str = False
                i += 1
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        # not in any literal/comment
        if c == "/" and nxt == "/":
            in_line_c = True
            out.append("  ")
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_c = 1
            out.append("  ")
            i += 2
            continue
        if c == '"' and text[i:i + 3] == '"""':
            in_triple = True
            out.append('"""')
            i += 3
            continue
        if c == '"':
            in_str = True
            out.append('"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_KOTLIN_LANGS = {"kt", "kotlin"}


def _iter_kotlin_blocks(text: str):
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _KOTLIN_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Pattern detection.
# ---------------------------------------------------------------------------


# Detect a class/object that implements X509TrustManager and has an
# obviously empty checkServerTrusted / checkClientTrusted method.
_TRUST_MANAGER_DECL_RE = re.compile(
    r"(?:class|object)\s+\w+\s*(?:\([^)]*\))?\s*:\s*"
    r"(?:[\w.]+\s*,\s*)*"
    r"X509(?:Extended)?TrustManager\b"
)

# Anonymous object literal: object : X509TrustManager { ... }
_ANON_TRUST_MANAGER_RE = re.compile(
    r"object\s*:\s*X509(?:Extended)?TrustManager\b"
)

# An override fun checkServerTrusted/checkClientTrusted whose body is
# empty (just whitespace inside braces) or a single "return" statement.
_EMPTY_CHECK_RE = re.compile(
    r"override\s+fun\s+(checkServerTrusted|checkClientTrusted)\s*"
    r"\([^)]*\)\s*(?::\s*[\w.<>?]+\s*)?\{\s*(?:return\s*;?\s*)?\}"
)

# getAcceptedIssuers returning emptyArray()/arrayOf()/null.
_EMPTY_ISSUERS_RE = re.compile(
    r"override\s+fun\s+getAcceptedIssuers\s*\([^)]*\)"
    r"\s*(?::\s*[\w.<>?]+\s*)?"
    r"(?:=\s*(?:emptyArray\s*<[^>]*>\s*\(\s*\)|emptyArray\s*\(\s*\)"
    r"|arrayOf\s*\(\s*\)|null)"
    r"|\{\s*return\s+(?:emptyArray\s*<[^>]*>\s*\(\s*\)|emptyArray\s*\(\s*\)"
    r"|arrayOf\s*\(\s*\)|null)\s*;?\s*\})"
)

# HostnameVerifier { _, _ -> true } and friends.
_HOSTNAME_LAMBDA_RE = re.compile(
    r"\.hostnameVerifier\s*(?:\(\s*HostnameVerifier\s*)?"
    r"\{\s*_?\w*\s*,\s*_?\w*\s*->\s*true\s*\}"
)

# Anonymous HostnameVerifier whose verify() returns true unconditionally.
_HOSTNAME_OBJECT_RE = re.compile(
    r"object\s*:\s*HostnameVerifier\s*\{[^{}]*?"
    r"override\s+fun\s+verify\s*\([^)]*\)\s*(?::\s*Boolean\s*)?"
    r"(?:=\s*true|\{\s*return\s+true\s*;?\s*\})",
    re.DOTALL,
)

# OkHttpClient.Builder() chain that calls .sslSocketFactory(...).
_BUILDER_SSL_RE = re.compile(
    r"OkHttpClient\s*(?:\.Builder)?\s*\([^)]*\)"
    r"(?:[^;{}]*?\.sslSocketFactory\s*\()"
)

# SSLContext.init(null, trustAllCerts, ...) — pretty strong signal.
_SSL_CONTEXT_INIT_RE = re.compile(
    r"\bSSLContext\b[^;{}\n]*\.init\s*\(\s*null\s*,\s*[\w\[\]]+\s*,"
)


def _line_of(text: str, idx: int, line_offset: int) -> int:
    return text.count("\n", 0, idx) + 1 + line_offset


def _suppressed(raw_lines: list[str], line_no: int) -> bool:
    if 1 <= line_no <= len(raw_lines):
        return SUPPRESS in raw_lines[line_no - 1]
    return False


def _scan_kotlin(
    raw: str,
    masked: str,
    raw_lines: list[str],
    line_offset: int,
    findings: list[tuple[int, str, str]],
) -> None:
    # 1. Trust manager shapes.
    for m in _EMPTY_CHECK_RE.finditer(masked):
        line = _line_of(masked, m.start(), line_offset)
        if _suppressed(raw_lines, line - line_offset):
            continue
        findings.append(
            (line, "trustall-trust-manager",
             f"empty {m.group(1)}() body — accepts any cert")
        )
    for m in _EMPTY_ISSUERS_RE.finditer(masked):
        line = _line_of(masked, m.start(), line_offset)
        if _suppressed(raw_lines, line - line_offset):
            continue
        findings.append(
            (line, "trustall-trust-manager",
             "getAcceptedIssuers returns empty/null")
        )

    # 2. Hostname verifier shapes.
    for m in _HOSTNAME_LAMBDA_RE.finditer(masked):
        line = _line_of(masked, m.start(), line_offset)
        if _suppressed(raw_lines, line - line_offset):
            continue
        findings.append(
            (line, "trustall-hostname-verifier",
             ".hostnameVerifier { _, _ -> true } accepts any host")
        )
    for m in _HOSTNAME_OBJECT_RE.finditer(masked):
        line = _line_of(masked, m.start(), line_offset)
        if _suppressed(raw_lines, line - line_offset):
            continue
        findings.append(
            (line, "trustall-hostname-verifier",
             "HostnameVerifier.verify() always returns true")
        )

    # 3. OkHttpClient builder hooked up to a trust-all SSL context.
    for m in _BUILDER_SSL_RE.finditer(masked):
        line = _line_of(masked, m.start(), line_offset)
        if _suppressed(raw_lines, line - line_offset):
            continue
        # Only flag the builder if SOME trust-all signal exists nearby
        # (same file). We've already collected those; cheap check:
        if (_EMPTY_CHECK_RE.search(masked) or
                _EMPTY_ISSUERS_RE.search(masked) or
                _SSL_CONTEXT_INIT_RE.search(masked)):
            findings.append(
                (line, "trustall-okhttp-builder",
                 "OkHttpClient.sslSocketFactory(...) wired to a "
                 "trust-all manager")
            )

    # 4. Direct SSLContext.init(null, X, ...) — independent signal.
    for m in _SSL_CONTEXT_INIT_RE.finditer(masked):
        line = _line_of(masked, m.start(), line_offset)
        if _suppressed(raw_lines, line - line_offset):
            continue
        findings.append(
            (line, "trustall-trust-manager",
             "SSLContext.init(null, <trust-all>, ...)")
        )


# ---------------------------------------------------------------------------
# File entrypoints.
# ---------------------------------------------------------------------------


def scan_text(text: str, suffix: str) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    if suffix in (".md", ".markdown"):
        for body, line_offset in _iter_kotlin_blocks(text):
            masked = _strip_strings_and_comments(body)
            raw_lines = body.splitlines()
            _scan_kotlin(body, masked, raw_lines, line_offset, findings)
    else:
        masked = _strip_strings_and_comments(text)
        raw_lines = text.splitlines()
        _scan_kotlin(text, masked, raw_lines, 0, findings)
    findings.sort(key=lambda t: (t[0], t[1]))
    return findings


def _iter_files(paths: list[str]):
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for sub in sorted(path.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SCAN_SUFFIXES:
                    yield sub
        elif path.is_file():
            if path.suffix.lower() in SCAN_SUFFIXES:
                yield path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    any_findings = False
    for f in _iter_files(argv[1:]):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"{f}: error reading: {exc}", file=sys.stderr)
            continue
        for line, kind, msg in scan_text(text, f.suffix.lower()):
            any_findings = True
            print(f"{f}:{line}: {kind}: {msg}")
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

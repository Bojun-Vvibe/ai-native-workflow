#!/usr/bin/env python3
"""Detect PHP ``unserialize()`` calls on attacker-reachable input.

The PHP ``unserialize()`` function instantiates arbitrary objects and
invokes magic methods (``__wakeup``, ``__destruct``, ``__toString``)
on the resulting graph. When fed untrusted bytes this is a classic
object-injection / RCE primitive (CWE-502).

This detector flags ``unserialize(<arg>)`` where ``<arg>`` is one of:

* a superglobal access — ``$_GET[...]``, ``$_POST[...]``, ``$_REQUEST[...]``,
  ``$_COOKIE[...]``, ``$_FILES[...]``, ``$_SERVER[...]``,
  ``$HTTP_RAW_POST_DATA``;
* a call to ``file_get_contents('php://input')`` or
  ``file_get_contents($_*)``;
* a variable whose name starts with one of the conventional
  "untrusted" prefixes (``$user_*``, ``$untrusted_*``, ``$payload``,
  ``$body``, ``$raw``, ``$input``, ``$cookie``, ``$req``, ``$request``);
* a chained ``base64_decode()`` / ``gzuncompress()`` /
  ``rawurldecode()`` of any of the above (the typical
  obfuscation-around-RCE shape).

PHP-aware token handling: ``//``, ``#``, and ``/* ... */`` comment
bodies are blanked, and the bodies of ``'...'``, ``"..."`` and
heredoc/nowdoc string literals are blanked. Suppression marker
(per-line, in a comment): ``// llm-allow:php-unserialize``.

The detector also extracts fenced ``php`` code from Markdown so README
worked examples and docs are scanned consistently.

Usage::

    python3 detect.py <file_or_dir> [...]

Exit ``1`` if any findings, ``0`` otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:php-unserialize"
SCAN_SUFFIXES = (".php", ".phtml", ".inc", ".md", ".markdown")

SUPERGLOBALS = (
    "$_GET",
    "$_POST",
    "$_REQUEST",
    "$_COOKIE",
    "$_FILES",
    "$_SERVER",
    "$HTTP_RAW_POST_DATA",
)

UNTRUSTED_VAR_PREFIXES = (
    "user_",
    "untrusted_",
    "payload",
    "body",
    "raw",
    "input",
    "cookie",
    "cookies",
    "req",
    "request",
    "post",
    "get",
    "params",
    "param",
)

DECODE_WRAPPERS = (
    "base64_decode",
    "gzuncompress",
    "gzinflate",
    "gzdecode",
    "rawurldecode",
    "urldecode",
    "hex2bin",
)


def _strip_strings_and_comments(text: str) -> str:
    """Blank out PHP comments and string-literal bodies, preserving
    line structure and quote/comment delimiters.

    Heredoc/nowdoc bodies are fully blanked (newlines preserved).
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_line_c = False  # // ... or # ...
    in_block_c = False  # /* ... */
    in_str: str | None = None  # '"' or "'"
    in_heredoc: str | None = None  # the closing label
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_c:
            if ch == "\n":
                in_line_c = False
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_c:
            if ch == "*" and nxt == "/":
                in_block_c = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_heredoc is not None:
            # Heredoc closes when, on its own line, the label appears
            # (optionally followed by `;` and EOL). To keep this simple
            # we look for "\n<label>" possibly preceded by whitespace
            # and followed by `;` or `\n`.
            label = in_heredoc
            # Try to detect end-of-heredoc at start of a line.
            if ch == "\n":
                # Peek the rest of next line.
                j = i + 1
                while j < n and text[j] in " \t":
                    j += 1
                if text.startswith(label, j):
                    end = j + len(label)
                    if end == n or text[end] in ";\n,)":
                        # End heredoc; emit newline + label, and let
                        # main loop continue from end.
                        out.append("\n")
                        out.append(" " * (j - (i + 1)))
                        out.append(label)
                        i = end
                        in_heredoc = None
                        continue
                out.append("\n")
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if in_str is not None:
            if in_str == '"' and ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == in_str:
                out.append(in_str)
                in_str = None
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        # Code mode.
        if ch == "/" and nxt == "/":
            in_line_c = True
            out.append("  ")
            i += 2
            continue
        if ch == "#":
            in_line_c = True
            out.append(" ")
            i += 1
            continue
        if ch == "/" and nxt == "*":
            in_block_c = True
            out.append("  ")
            i += 2
            continue
        if ch == "<" and text.startswith("<<<", i):
            # Heredoc/nowdoc start: <<<LABEL or <<<"LABEL" or <<<'LABEL'
            j = i + 3
            # Optional quote
            quote = ""
            if j < n and text[j] in "\"'":
                quote = text[j]
                j += 1
            label_start = j
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            label = text[label_start:j]
            if quote:
                if j < n and text[j] == quote:
                    j += 1
                else:
                    # Malformed; treat as code.
                    out.append(ch)
                    i += 1
                    continue
            # Skip to end-of-line.
            while j < n and text[j] != "\n":
                j += 1
            if not label:
                out.append(ch)
                i += 1
                continue
            # Emit "<<<LABEL" + spaces for any quote, then newline.
            out.append("<<<" + label)
            out.append(" " * (j - (i + 3 + len(label))))
            # Move past newline.
            if j < n:
                out.append("\n")
                j += 1
            in_heredoc = label
            i = j
            continue
        if ch in ("'", '"'):
            in_str = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _find_matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    n = len(text)
    i = open_idx
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_text(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


RE_UNSERIALIZE = re.compile(r"(?<![A-Za-z0-9_>])unserialize\s*\(")


def _arg_is_untrusted(arg_clean: str, arg_orig: str) -> str | None:
    """Return a short reason string if the argument looks untrusted."""
    s = arg_clean.strip()
    if not s:
        return None
    # Strip a leading decode wrapper if present (one-deep is enough to
    # cover the common obfuscation shape; nested wrappers also match
    # because we recurse into the inner arg).
    for w in DECODE_WRAPPERS:
        m = re.match(re.escape(w) + r"\s*\(", s)
        if m:
            inner_open = m.end() - 1
            inner_close = _find_matching_paren(s, inner_open)
            if inner_close == -1:
                continue
            inner_clean = s[inner_open + 1 : inner_close]
            inner_orig = arg_orig.strip()
            mo = re.match(re.escape(w) + r"\s*\(", inner_orig)
            inner_orig_arg = inner_orig
            if mo:
                io = mo.end() - 1
                ic = _find_matching_paren(inner_orig, io)
                if ic != -1:
                    inner_orig_arg = inner_orig[io + 1 : ic]
            inner_reason = _arg_is_untrusted(inner_clean, inner_orig_arg)
            if inner_reason:
                return f"decoded({w})->" + inner_reason
            return None
    # Superglobal access.
    for sg in SUPERGLOBALS:
        if re.match(re.escape(sg) + r"(?![A-Za-z0-9_])", s):
            return f"superglobal {sg}"
    # file_get_contents('php://input') or file_get_contents($_*)
    m = re.match(r"file_get_contents\s*\(", s)
    if m:
        inner_open = m.end() - 1
        inner_close = _find_matching_paren(s, inner_open)
        if inner_close != -1:
            inner = s[inner_open + 1 : inner_close].strip()
            inner_orig_full = arg_orig.strip()
            mo = re.match(r"file_get_contents\s*\(", inner_orig_full)
            inner_orig_arg = ""
            if mo:
                io = mo.end() - 1
                ic = _find_matching_paren(inner_orig_full, io)
                if ic != -1:
                    inner_orig_arg = inner_orig_full[io + 1 : ic]
            # If the literal string contains "php://input" treat as untrusted.
            if "php://input" in inner_orig_arg:
                return "file_get_contents(php://input)"
            for sg in SUPERGLOBALS:
                if sg in inner:
                    return f"file_get_contents({sg}...)"
            # Variable arg with untrusted-looking name.
            mv = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)", inner)
            if mv and _name_is_untrusted(mv.group(1)):
                return f"file_get_contents(${mv.group(1)})"
    # Bare variable with untrusted-looking name.
    mv = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)", s)
    if mv and _name_is_untrusted(mv.group(1)):
        # But require the rest of the expression to be just the var
        # (allow trailing whitespace / nothing).
        rest = s[mv.end():].strip()
        if rest in ("", ","):
            return f"untrusted-named-var ${mv.group(1)}"
    return None


def _name_is_untrusted(name: str) -> bool:
    low = name.lower()
    if low in UNTRUSTED_VAR_PREFIXES:
        return True
    for p in UNTRUSTED_VAR_PREFIXES:
        if low.startswith(p):
            return True
    return False


def scan_text_php(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_strings_and_comments(text)
    pos = 0
    while True:
        m = RE_UNSERIALIZE.search(cleaned, pos)
        if not m:
            break
        open_idx = m.end() - 1
        close_idx = _find_matching_paren(cleaned, open_idx)
        if close_idx == -1:
            pos = m.end()
            continue
        arg_clean = cleaned[open_idx + 1 : close_idx]
        arg_orig = text[open_idx + 1 : close_idx]
        # Only look at first positional argument (PHP unserialize takes
        # 1 or 2 args; the second is the allowed_classes options array
        # which does not change exploitability when passed
        # ['allowed_classes'=>true] or default).
        # Split on first top-level comma.
        depth = 0
        first_end = len(arg_clean)
        for i, c in enumerate(arg_clean):
            if c in "({[":
                depth += 1
            elif c in ")}]":
                depth -= 1
            elif c == "," and depth == 0:
                first_end = i
                break
        first_clean = arg_clean[:first_end]
        first_orig = arg_orig[:first_end]
        reason = _arg_is_untrusted(first_clean, first_orig)
        if reason:
            lineno = _line_of_offset(cleaned, m.start())
            end_line = _line_of_offset(cleaned, close_idx)
            suppressed = any(
                SUPPRESS in _line_text(text, ln)
                for ln in range(max(1, lineno - 1), end_line + 1)
            )
            if not suppressed:
                findings.append(
                    (
                        path,
                        lineno,
                        f"unsafe-unserialize({reason})",
                        _line_text(text, lineno).rstrip(),
                    )
                )
        pos = close_idx + 1
    return findings


RE_FENCE_OPEN = re.compile(
    r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$"
)


def _md_extract_php(text: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    pos = 0
    while True:
        m = RE_FENCE_OPEN.search(text, pos)
        if not m:
            return out
        fence = m.group(1)
        lang = (m.group(2) or "").lower()
        body_start = m.end() + 1
        close_re = re.compile(
            r"(?m)^" + fence[0] + "{" + str(len(fence)) + r",}[ \t]*$"
        )
        cm = close_re.search(text, body_start)
        if not cm:
            return out
        if lang in ("php", "phtml", ""):
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_php(text):
        body = text[body_start:body_end]
        sub = scan_text_php(path, body)
        offset_lines = text.count("\n", 0, body_start)
        for p, ln, kind, line in sub:
            findings.append((p, ln + offset_lines, kind, line))
    return findings


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    suf = path.suffix.lower()
    if suf in (".md", ".markdown"):
        return scan_text_md(path, text)
    return scan_text_php(path, text)


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SCAN_SUFFIXES:
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

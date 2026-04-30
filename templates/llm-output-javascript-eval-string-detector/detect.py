#!/usr/bin/env python3
"""Detect JavaScript ``eval(...)`` and ``new Function(...)`` calls
where the argument is *not* a single static string literal — the
canonical CWE-95 (Improper Neutralization of Directives in
Dynamically Evaluated Code, "Eval Injection") shape.

Concretely, a finding is emitted whenever:

* ``eval(`` is called and the argument expression contains a
  non-literal element (an identifier, member access, template
  literal interpolation ``${...}``, or string concatenation with a
  non-literal), OR
* ``new Function(`` is called with one or more arguments where the
  *last* argument (the function body) is not a single static
  string literal.

A bare ``eval("1 + 1")`` with a single static string literal is NOT
flagged — it is still bad style but not an injection sink.

Examples flagged::

    eval(userInput);
    eval("var x = " + userInput);
    eval(`return ${expr};`);
    new Function("x", "y", body);
    new Function(req.body.code);
    window.eval(input);
    globalThis.eval(input);

Examples NOT flagged::

    eval("1 + 1");                           // static literal
    new Function("x", "y", "return x + y;"); // static literal body
    JSON.parse(text);                        // not eval
    setTimeout(fn, 1000);                    // function ref not string

Suppress with ``// llm-allow:js-eval-dynamic`` on the same logical
line as the call.

Stdlib only. Exit 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// llm-allow:js-eval-dynamic"

SCAN_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
                 ".md", ".markdown")


def _strip_js_strings_and_comments(text: str) -> str:
    """Mask JavaScript ``//``, ``/* */`` comments and the *interiors*
    of string and template literals. Outer delimiters (``"``, ``'``,
    `` ` ``) are preserved so the call-shape regex can see ``eval("`` /
    ``eval(`` etc., but the contents are blanked. Inside template
    literals we also expose ``${`` / ``}`` boundaries (so the caller
    can tell "the template had an interpolation"). Newlines are
    preserved.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_line_c = False
    in_block_c = False
    in_str: str | None = None  # one of '"', "'", '`'
    template_depth = 0  # nesting of ${ ... } inside a template
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_c:
            if c == "\n":
                in_line_c = False
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_c:
            if c == "*" and nxt == "/":
                in_block_c = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if in_str is not None:
            if in_str == "`":
                # Template literal handling.
                if c == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if c == "$" and nxt == "{":
                    out.append("${")
                    template_depth += 1
                    i += 2
                    # Now we're back in code mode while inside the
                    # template — but for simplicity, we treat the
                    # interior as code. Pop in_str temporarily.
                    in_str = None
                    continue
                if c == "`":
                    out.append("`")
                    in_str = None
                    i += 1
                    continue
                out.append("\n" if c == "\n" else " ")
                i += 1
                continue
            # Regular string.
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == in_str:
                out.append(in_str)
                in_str = None
                i += 1
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        # Code mode.
        if template_depth > 0 and c == "}":
            template_depth -= 1
            out.append("}")
            in_str = "`"
            i += 1
            continue
        if c == "/" and nxt == "/":
            in_line_c = True
            out.append("  ")
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_c = True
            out.append("  ")
            i += 2
            continue
        if c in ('"', "'", "`"):
            in_str = c
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _line_of(text: str, off: int) -> int:
    return text.count("\n", 0, off) + 1


def _line_text(text: str, ln: int) -> str:
    lines = text.splitlines()
    if 1 <= ln <= len(lines):
        return lines[ln - 1]
    return ""


def _find_matching_paren(s: str, open_idx: int) -> int:
    depth = 0
    n = len(s)
    i = open_idx
    while i < n:
        c = s[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _split_top_args(s: str) -> list[str]:
    """Split a parenthesized argument list (without the enclosing
    parens) on top-level commas."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for c in s:
        if c in "([{":
            depth += 1
            cur.append(c)
        elif c in ")]}":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if cur:
        parts.append("".join(cur))
    return [p.strip() for p in parts]


# A "static literal" expression is one that is exactly a single
# string literal token (no concatenation, no interpolation, no
# identifier). After string-interior masking, a literal
# `"foo bar"` becomes `"        "` — i.e. a quote, blanks, a quote.
RE_STATIC_LITERAL = re.compile(
    r"""^\s*(?:
        "[^"\n]*"          # double-quoted (interior already blanked)
      | '[^'\n]*'          # single-quoted
      | `[^`$]*`           # template w/ no interpolation
    )\s*$""",
    re.VERBOSE,
)


def _is_static_literal(arg_clean: str) -> bool:
    return bool(RE_STATIC_LITERAL.match(arg_clean))


# eval( — including window.eval(, globalThis.eval(, self.eval(.
RE_EVAL_CALL = re.compile(
    r"(?<![A-Za-z0-9_$.])"
    r"(?:(?:window|self|globalThis|global)\s*\.\s*)?"
    r"eval\s*\("
)

# new Function( — the constructor form. Not Function.prototype.* ,
# not function() {}, not someObj.Function (). The lookbehind avoids
# matching inside identifiers.
RE_NEW_FUNCTION = re.compile(
    r"(?<![A-Za-z0-9_$])new\s+Function\s*\("
)


def scan_text_js(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    cleaned = _strip_js_strings_and_comments(text)

    # eval(...)
    pos = 0
    while True:
        m = RE_EVAL_CALL.search(cleaned, pos)
        if not m:
            break
        open_paren = m.end() - 1
        close = _find_matching_paren(cleaned, open_paren)
        args = cleaned[open_paren + 1:close]
        arg_list = _split_top_args(args)
        # eval takes exactly one arg in practice; if zero, skip.
        if not arg_list or arg_list == [""]:
            pos = close + 1
            continue
        first = arg_list[0]
        if not _is_static_literal(first):
            ln = _line_of(text, m.start())
            end_ln = _line_of(text, close)
            suppressed = any(
                SUPPRESS in _line_text(text, k)
                for k in range(max(1, ln), end_ln + 1)
            )
            if not suppressed:
                findings.append(
                    (path, ln, "js-eval-dynamic",
                     _line_text(text, ln).rstrip())
                )
        pos = close + 1

    # new Function(...)
    pos = 0
    while True:
        m = RE_NEW_FUNCTION.search(cleaned, pos)
        if not m:
            break
        open_paren = m.end() - 1
        close = _find_matching_paren(cleaned, open_paren)
        args = cleaned[open_paren + 1:close]
        arg_list = _split_top_args(args)
        if not arg_list or arg_list == [""]:
            # `new Function()` with zero args is harmless.
            pos = close + 1
            continue
        body = arg_list[-1]
        if not _is_static_literal(body):
            ln = _line_of(text, m.start())
            end_ln = _line_of(text, close)
            suppressed = any(
                SUPPRESS in _line_text(text, k)
                for k in range(max(1, ln), end_ln + 1)
            )
            if not suppressed:
                findings.append(
                    (path, ln, "js-new-function-dynamic-body",
                     _line_text(text, ln).rstrip())
                )
        pos = close + 1

    return findings


RE_FENCE_OPEN = re.compile(r"(?m)^([`~]{3,})[ \t]*([A-Za-z0-9_+\-./]*)[^\n]*$")
JS_FENCE_LANGS = {"js", "javascript", "jsx", "ts", "tsx", "typescript",
                  "mjs", "cjs", "node", ""}


def _md_extract_js(text: str) -> list[tuple[int, int]]:
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
        if lang in JS_FENCE_LANGS:
            out.append((body_start, cm.start()))
        pos = cm.end()


def scan_text_md(path: Path, text: str) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for body_start, body_end in _md_extract_js(text):
        body = text[body_start:body_end]
        sub = scan_text_js(path, body)
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
    return scan_text_js(path, text)


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

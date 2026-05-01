#!/usr/bin/env python3
"""
llm-output-go-html-template-raw-injection-detector

Flags Go source where the auto-escaping discipline of ``html/template``
is *bypassed* by wrapping a runtime value in one of the
"trusted-content" marker types:

    template.HTML(s)   // emits s literally as HTML body
    template.JS(s)     // emits s literally inside <script>
    template.JSStr(s)  // emits s literally inside a JS string ctx
    template.CSS(s)    // emits s literally inside <style>
    template.URL(s)    // emits s literally as a URL attribute value
    template.HTMLAttr(s)
    template.Srcset(s)

These conversions tell ``html/template`` "trust me, this string is
already safe in this context, do not escape it." When the wrapped
value is anything other than a compile-time string literal, an
attacker-controlled value flows straight into the rendered page —
the canonical CWE-79 (Cross-Site Scripting) shape in Go templates.

A LLM under pressure to "render this snippet of HTML I built" will
write::

    fmt.Fprintln(w, template.HTML(userBio))             // XSS
    js := template.JS("console.log('"+username+"');")   // XSS

instead of letting the template engine escape::

    tmpl.Execute(w, map[string]any{"Bio": userBio})      // safe
    // {{ .Bio }} in the template — html/template escapes per ctx

The detector flags two kinds:

1. **go-html-template-bypass-runtime** — a call to one of the
   marker-type constructors (``template.HTML``, ``template.JS``,
   ``template.JSStr``, ``template.CSS``, ``template.URL``,
   ``template.HTMLAttr``, ``template.Srcset``) whose argument is
   *not* a plain string literal or an all-literal ``+`` chain.

2. **go-html-template-bypass-format** — the same constructors wrapped
   around a ``fmt.Sprintf`` / ``fmt.Sprint`` / ``fmt.Sprintln`` call,
   even if every other heuristic would otherwise miss it.

A finding is suppressed if the same logical line carries the
trailing comment ``// llm-allow:go-template-raw``.

Single-line ``//`` comments and ``/* ... */`` block comments are
masked before analysis. Fenced ``go`` code blocks are extracted from
Markdown.

Stdlib only. Reads files passed on argv (or recurses into directories
for *.go / *.md / *.markdown). Exit code 1 if any findings, 0
otherwise, 2 on usage error.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

SUPPRESS = "// llm-allow:go-template-raw"

SCAN_SUFFIXES = (".go", ".md", ".markdown")

MARKER_TYPES = (
    "HTML",
    "JS",
    "JSStr",
    "CSS",
    "URL",
    "HTMLAttr",
    "Srcset",
)


# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_GO_LANGS = {"go", "golang"}


def _iter_go_blocks(text: str) -> Iterable[Tuple[str, int]]:
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _GO_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Comment + raw-string-literal masking.
#
# Go has three string forms:
#   "double quoted"   - escapes apply
#   `back-tick raw`   - no escapes, can span newlines
#   '...rune...'      - single rune
#
# Comments: // line, /* block */
#
# We mask comments to spaces (preserve newlines). String literals are
# left intact because we *want* to recognize literal arguments.
# ---------------------------------------------------------------------------
def _mask_comments(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            if j < 0:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (j - i))
                i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                seg = text[i:]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = n
            else:
                seg = text[i : j + 2]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = j + 2
        elif c == '"':
            # double-quoted string: skip but keep contents
            out.append(c)
            i += 1
            while i < n:
                if text[i] == "\\":
                    if i + 1 < n:
                        out.append(text[i])
                        out.append(text[i + 1])
                        i += 2
                        continue
                    out.append(text[i])
                    i += 1
                    continue
                out.append(text[i])
                if text[i] == '"':
                    i += 1
                    break
                i += 1
        elif c == "`":
            # raw string: skip but keep contents (incl. newlines)
            out.append(c)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "`":
                    i += 1
                    break
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Detector core.
# ---------------------------------------------------------------------------

# Match: <pkg>.HTML(  where pkg is "template" (incl. aliased as
# htmltemplate) — we accept any short ident before the dot, then
# verify the type name is in MARKER_TYPES.
_MARKER_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*("
    + "|".join(MARKER_TYPES)
    + r")\s*\("
)

_LITERAL_DOUBLE = re.compile(r'^"(?:[^"\\]|\\.)*"$', re.DOTALL)
_LITERAL_RAW = re.compile(r"^`[^`]*`$", re.DOTALL)


def _is_string_literal(s: str) -> bool:
    s = s.strip()
    return bool(_LITERAL_DOUBLE.match(s) or _LITERAL_RAW.match(s))


def _is_literal_concat(s: str) -> bool:
    """True if s is a chain of string literals joined by `+`."""
    s = s.strip()
    if _is_string_literal(s):
        return True
    # crude split on top-level + (no parens) — sufficient for common LLM
    # output: "a" + "b" + "c"
    depth = 0
    parts: List[str] = []
    cur = []
    in_dq = False
    in_raw = False
    i = 0
    while i < len(s):
        ch = s[i]
        if not in_dq and not in_raw:
            if ch == '"':
                in_dq = True
                cur.append(ch)
                i += 1
                continue
            if ch == "`":
                in_raw = True
                cur.append(ch)
                i += 1
                continue
            if ch == "(":
                depth += 1
                cur.append(ch)
                i += 1
                continue
            if ch == ")":
                depth -= 1
                cur.append(ch)
                i += 1
                continue
            if ch == "+" and depth == 0:
                parts.append("".join(cur))
                cur = []
                i += 1
                continue
        else:
            if in_dq:
                cur.append(ch)
                if ch == "\\" and i + 1 < len(s):
                    cur.append(s[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    in_dq = False
                i += 1
                continue
            if in_raw:
                cur.append(ch)
                if ch == "`":
                    in_raw = False
                i += 1
                continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    if len(parts) <= 1:
        return False
    return all(_is_string_literal(p) for p in parts)


def _balanced_paren_end(text: str, start: int) -> int:
    depth = 0
    i = start
    n = len(text)
    in_dq = False
    in_raw = False
    while i < n:
        c = text[i]
        if in_dq:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == '"':
                in_dq = False
            i += 1
            continue
        if in_raw:
            if c == "`":
                in_raw = False
            i += 1
            continue
        if c == '"':
            in_dq = True
            i += 1
            continue
        if c == "`":
            in_raw = True
            i += 1
            continue
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth -= 1
            if depth == 0:
                return i
            i += 1
            continue
        i += 1
    return -1


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _scan_source(src: str, base_line: int, path: str) -> List[str]:
    findings: List[str] = []
    masked = _mask_comments(src)
    raw_lines = src.splitlines()
    for m in _MARKER_RE.finditer(masked):
        pkg = m.group(1)
        type_name = m.group(2)
        # Accept common aliases for the html/template import.
        if pkg not in ("template", "htmltemplate", "htmlt", "htmltmpl"):
            continue
        paren_open = m.end() - 1
        paren_close = _balanced_paren_end(masked, paren_open)
        if paren_close < 0:
            continue
        inner = masked[paren_open + 1 : paren_close].strip()
        if not inner:
            continue
        line_no = _line_of(src, m.start()) + base_line
        line_idx = line_no - base_line - 1
        if 0 <= line_idx < len(raw_lines):
            snippet = raw_lines[line_idx].strip()
        else:
            snippet = ""
        if len(snippet) > 100:
            snippet = snippet[:97] + "..."

        # SUPPRESS check: scan source line + closing-paren line.
        sup_window_end = src.find("\n", paren_close)
        if sup_window_end < 0:
            sup_window_end = len(src)
        if SUPPRESS in src[m.start() : sup_window_end]:
            continue

        # Static literal or all-literal concat → fine.
        if _is_literal_concat(inner):
            continue

        # fmt.Sprintf / Sprint / Sprintln wrap → distinct kind.
        if re.match(r"^fmt\s*\.\s*(Sprintf|Sprint|Sprintln)\s*\(", inner):
            findings.append(
                f"{path}:{line_no}: go-html-template-bypass-format: "
                f"template.{type_name}(fmt.Sprintf...) bypasses html/template auto-escape (CWE-79): {snippet}"
            )
            continue

        findings.append(
            f"{path}:{line_no}: go-html-template-bypass-runtime: "
            f"template.{type_name}(<runtime value>) bypasses html/template auto-escape (CWE-79): {snippet}"
        )
    return findings


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if path.endswith((".md", ".markdown")):
        for body, off in _iter_go_blocks(text):
            findings.extend(_scan_source(body, off, path))
    else:
        findings.extend(_scan_source(text, 0, path))
    return findings


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.endswith(SCAN_SUFFIXES):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

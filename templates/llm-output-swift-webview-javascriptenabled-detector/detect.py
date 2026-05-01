#!/usr/bin/env python3
"""Detect Swift / Objective-C WebView configurations that enable
JavaScript on a content surface that is exposed to untrusted HTML.

Targets:

* ``UIWebView`` — Apple-deprecated, JavaScript is on by default and the
  whole class is the canonical CWE-79 (XSS) vehicle on iOS. Any
  construction or use is flagged.
* ``WKWebView`` configured with
  ``WKWebViewConfiguration.preferences.javaScriptEnabled = true`` or
  ``WKWebpagePreferences.allowsContentJavaScript = true``.
* ``WKWebView.evaluateJavaScript(<non-literal>)`` — string-built JS
  injected into the page (CWE-79 via reflected DOM injection).
* ``loadHTMLString(<non-literal>, baseURL: ...)`` where the HTML body
  is not a string literal — typical "render the markdown the server
  sent us" LLM shape.

Suppression marker (per-line, in a ``//`` comment):
``// llm-allow:swift-webview-js``.

Markdown ``swift`` / ``objc`` / ``objective-c`` fenced blocks are
extracted so README worked examples and docs are scanned consistently.

Usage::

    python3 detect.py <file_or_dir> [...]

Exit ``1`` if any findings, ``0`` otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "llm-allow:swift-webview-js"
SCAN_SUFFIXES = (".swift", ".m", ".mm", ".h", ".md", ".markdown")

# --- token-aware blanking -------------------------------------------------
# Swift strings: "..." and triple-quoted """..."""; Obj-C: "..." and @"...".
# Comments: //, /* */.

_TOKEN_RE = re.compile(
    r"""
    (?P<bs>  /\*.*?\*/                                     ) |  # block comment
    (?P<ls>  //[^\n]*                                      ) |  # line comment
    (?P<tq>  \"\"\"(?:\\.|[^\\])*?\"\"\"                   ) |  # triple-quoted Swift
    (?P<dq>  @?\"(?:\\.|[^\"\\\n])*\"                      )    # "..." or @"..."
    """,
    re.VERBOSE | re.DOTALL,
)


def _blank(src: str) -> str:
    out = []
    i = 0
    for m in _TOKEN_RE.finditer(src):
        out.append(src[i:m.start()])
        body = m.group(0)
        out.append("".join(c if c == "\n" else " " for c in body))
        i = m.end()
    out.append(src[i:])
    return "".join(out)


# --- markdown fence extraction -------------------------------------------

_FENCE_RE = re.compile(
    r"^```\s*(swift|objc|objective-c|objectivec|m)\b[^\n]*\n"
    r"(?P<body>.*?)"
    r"^```",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _extract_md_blocks(src: str) -> str:
    out_lines = src.splitlines(keepends=True)
    keep = [" " * (len(l) - 1) + "\n" if l.endswith("\n") else " " * len(l)
            for l in out_lines]
    for m in _FENCE_RE.finditer(src):
        start_line = src.count("\n", 0, m.start("body"))
        body = m.group("body")
        body_lines = body.splitlines(keepends=True)
        for j, bl in enumerate(body_lines):
            idx = start_line + j
            if idx < len(keep):
                keep[idx] = bl
    return "".join(keep)


# --- pattern set ---------------------------------------------------------

# UIWebView reference (construction or type usage).
_UIWEBVIEW_RE = re.compile(r"\bUIWebView\b")

# javaScriptEnabled = true (and Swift bool literal `true`)
_JS_ENABLED_RE = re.compile(
    r"\bjavaScriptEnabled\s*=\s*true\b"
)

# allowsContentJavaScript = true
_ALLOWS_CONTENT_JS_RE = re.compile(
    r"\ballowsContentJavaScript\s*=\s*true\b"
)

# .evaluateJavaScript(<arg>) — flagged when arg is not a pure literal.
_EVAL_JS_RE = re.compile(
    r"\.evaluateJavaScript\s*\("
)

# .loadHTMLString(<html>, baseURL: ...) — flagged when html is not literal.
_LOAD_HTML_RE = re.compile(
    r"\.loadHTMLString\s*\("
)


def _find_call_args(src: str, open_paren_idx: int):
    depth = 0
    i = open_paren_idx
    n = len(src)
    while i < n:
        c = src[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return src[open_paren_idx + 1:i], i + 1
        i += 1
    return None, None


def _first_arg(args: str) -> str:
    """Return text of the first comma-separated argument (depth-aware)."""
    depth = 0
    for i, c in enumerate(args):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            return args[:i]
    return args


_LITERAL_STRING_RE = re.compile(
    r"""\A\s*
        (
            \"\"\".*\"\"\"            # triple-quoted Swift
          | @?\"(?:\\.|[^\"\\\n])*\"  # plain "..."
        )
        \s*\Z
    """,
    re.VERBOSE | re.DOTALL,
)


def _scan(text: str, path: Path):
    findings = []
    md = path.suffix.lower() in (".md", ".markdown")
    src = _extract_md_blocks(text) if md else text
    blanked = _blank(src)
    raw_lines = text.splitlines()

    def _emit(idx: int, kind: str, detail: str):
        line_no = blanked.count("\n", 0, idx) + 1
        if line_no - 1 < len(raw_lines) and SUPPRESS in raw_lines[line_no - 1]:
            return
        findings.append(f"{path}:{line_no}: {kind}({detail})")

    for m in _UIWEBVIEW_RE.finditer(blanked):
        _emit(m.start(), "swift-uiwebview", "UIWebView")

    for m in _JS_ENABLED_RE.finditer(blanked):
        _emit(m.start(), "swift-webview-jsenabled", "javaScriptEnabled=true")

    for m in _ALLOWS_CONTENT_JS_RE.finditer(blanked):
        _emit(m.start(), "swift-webview-jsenabled",
              "allowsContentJavaScript=true")

    for m in _EVAL_JS_RE.finditer(blanked):
        open_idx = m.end() - 1
        args, _ = _find_call_args(src, open_idx)  # original src for literal check
        if args is None:
            continue
        first = _first_arg(args).strip()
        if _LITERAL_STRING_RE.match(first):
            continue
        _emit(m.start(), "swift-webview-evaljs-nonliteral", "evaluateJavaScript")

    for m in _LOAD_HTML_RE.finditer(blanked):
        open_idx = m.end() - 1
        args, _ = _find_call_args(src, open_idx)
        if args is None:
            continue
        first = _first_arg(args).strip()
        if _LITERAL_STRING_RE.match(first):
            continue
        _emit(m.start(), "swift-webview-loadhtml-nonliteral", "loadHTMLString")

    return findings


def _iter_paths(roots):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for q in sorted(p.rglob("*")):
                if q.is_file() and q.suffix.lower() in SCAN_SUFFIXES:
                    yield q
        elif p.is_file():
            yield p


def main(argv):
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings = []
    for path in _iter_paths(argv[1:]):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"{path}: read-error: {e}", file=sys.stderr)
            continue
        findings.extend(_scan(text, path))
    for f in findings:
        print(f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

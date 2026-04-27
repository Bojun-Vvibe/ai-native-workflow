#!/usr/bin/env python3
"""Detect raw HTML block-leading lines in markdown output.

LLMs commonly fall back to raw HTML (<div>, <table>, <details>,
<br>, <hr>, <img>, etc.) inside markdown when they cannot express a
construct cleanly. This detector flags any line that begins
(after optional indent) with a recognized HTML block-level open tag
or void tag.

Code-fence aware: lines inside ``` or ~~~ fences are skipped.
HTML comments (<!-- ... -->) are ignored.
Inline HTML mid-paragraph is not flagged; only block-leading HTML.

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")

# Recognized HTML block-level / void tag names (CommonMark group 6
# plus common void tags LLMs leak).
BLOCK_TAGS = {
    "address", "article", "aside", "base", "basefont", "blockquote",
    "body", "br", "button", "canvas", "caption", "center", "col",
    "colgroup", "dd", "details", "dialog", "dir", "div", "dl", "dt",
    "embed", "fieldset", "figcaption", "figure", "footer", "form",
    "frame", "frameset", "h1", "h2", "h3", "h4", "h5", "h6", "head",
    "header", "hr", "html", "iframe", "img", "input", "legend", "li",
    "link", "main", "menu", "menuitem", "meta", "nav", "noframes",
    "ol", "optgroup", "option", "p", "param", "picture", "pre",
    "section", "select", "source", "summary", "table", "tbody", "td",
    "template", "textarea", "tfoot", "th", "thead", "title", "tr",
    "track", "ul", "video", "wbr",
}

# Match an opening or self-closing tag at start of trimmed line.
TAG_RE = re.compile(r"^<\s*([A-Za-z][A-Za-z0-9]*)\b[^>]*/?\s*>")
COMMENT_RE = re.compile(r"^<!--")


def scan(text: str):
    in_fence = False
    findings = []
    for i, raw in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = raw.lstrip()
        if not stripped.startswith("<"):
            continue
        if COMMENT_RE.match(stripped):
            continue
        m = TAG_RE.match(stripped)
        if not m:
            continue
        tag = m.group(1).lower()
        if tag in BLOCK_TAGS:
            findings.append((i, tag, raw.rstrip("\n")))
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    findings = scan(text)
    for line, tag, raw in findings:
        print(f"{argv[1]}:{line}: html-block tag <{tag}>: {raw}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

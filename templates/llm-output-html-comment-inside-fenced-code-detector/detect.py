#!/usr/bin/env python3
"""Detect HTML comments (<!-- ... -->) inside fenced code blocks
whose declared language is not an HTML/XML/Markdown-family language.

Usage:  python3 detect.py <markdown-file>
Exit:   0 = clean, 1 = findings, 2 = usage/IO error.
"""
from __future__ import annotations

import re
import sys

# Languages where <!-- --> is legitimate. Everything else is suspect.
HTML_FAMILY = {
    "html", "htm", "xml", "svg", "xhtml",
    "markdown", "md", "mdx",
    "vue", "jsx", "tsx", "astro",
    "liquid", "handlebars", "hbs", "mustache", "ejs",
    "nunjucks", "jinja", "jinja2", "j2", "erb",
    "razor", "cshtml", "php", "aspx",
}

FENCE_RE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})\s*(?P<info>[^\n]*)$")


def parse_lang(info: str) -> str:
    info = info.strip()
    if not info:
        return ""
    # Info string: language is the first whitespace-separated token,
    # stripped of braces / commas / colons.
    tok = re.split(r"[\s,]", info, maxsplit=1)[0]
    tok = tok.strip("{}").strip()
    if tok.startswith("."):
        tok = tok[1:]
    return tok.lower()


def scan(text: str):
    """Yield (line, col, kind, lang, snippet) tuples."""
    lines = text.splitlines()
    i = 0
    findings = []
    while i < len(lines):
        line = lines[i]
        m = FENCE_RE.match(line)
        if not m:
            i += 1
            continue
        fence = m.group("fence")
        fence_char = fence[0]
        fence_len = len(fence)
        lang = parse_lang(m.group("info"))
        # Find matching closing fence.
        start_line = i  # 0-indexed
        j = i + 1
        body_lines = []
        closed = False
        while j < len(lines):
            cm = re.match(
                r"^[ ]{0,3}(" + re.escape(fence_char) + r"{" + str(fence_len) + r",})\s*$",
                lines[j],
            )
            if cm:
                closed = True
                break
            body_lines.append((j, lines[j]))
            j += 1
        # Decide whether to scan this body for HTML comments.
        if lang not in HTML_FAMILY:
            findings.extend(_scan_body(body_lines, lang or "(none)"))
        # Advance past this fence.
        i = j + 1 if closed else len(lines)
    return findings


def _scan_body(body_lines, lang_label: str):
    """Scan the body of one code fence for <!-- ... --> patterns.

    body_lines: list of (line_idx_0based, raw_line).
    """
    out = []
    if not body_lines:
        return out
    # Reconstruct text and a parallel mapping from offset -> (line, col).
    pieces = []
    offset_map = []  # list of (line_1based, col_1based) per char
    for li, raw in body_lines:
        for ci, ch in enumerate(raw):
            pieces.append(ch)
            offset_map.append((li + 1, ci + 1))
        pieces.append("\n")
        offset_map.append((li + 1, len(raw) + 1))
    blob = "".join(pieces)
    pos = 0
    while True:
        start = blob.find("<!--", pos)
        if start == -1:
            break
        end = blob.find("-->", start + 4)
        line, col = offset_map[start]
        if end == -1:
            out.append((line, col, "unterminated_comment_in_code", lang_label, "<!--"))
            break
        snippet_full = blob[start:end + 3]
        snippet = snippet_full.replace("\n", " ").strip()
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        out.append((line, col, "html_comment_in_code", lang_label, snippet))
        pos = end + 3
    return out


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: detect.py <markdown-file>\n")
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"io error: {e}\n")
        return 2
    findings = scan(text)
    findings.sort(key=lambda t: (t[0], t[1], t[2]))
    for line, col, kind, lang, snippet in findings:
        print(f"{line}:{col} {kind} lang={lang} {snippet}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

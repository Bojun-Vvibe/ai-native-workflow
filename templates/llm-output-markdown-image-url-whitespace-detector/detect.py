#!/usr/bin/env python3
"""Detect markdown image references whose URL contains whitespace.

LLMs frequently emit image syntax of the form:

    ![diagram](assets/system diagram.png)

Markdown renderers split the parenthesised content on the first
whitespace; the first token is treated as the URL and anything that
follows is expected to be a quoted title. A bare second token (no
quotes) makes the entire image reference malformed and the image
silently fails to render.

Valid forms are:

    ![alt](no-space-url.png)
    ![alt](url-with-encoded%20space.png)
    ![alt](url.png "title with spaces is fine when quoted")

This detector flags `![alt](url ...)` constructs where:
  - the URL token is followed by non-title content (no leading quote)
  - or the URL itself contains a tab character (always invalid)

It is **code-fence aware** (skips ``` and ~~~ blocks) and ignores
inline-code spans (text between single backticks on the same line).

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")

# Match ![alt](inside) where 'inside' has no nested parens. We then
# inspect 'inside' ourselves to decide if the URL is well-formed.
IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\n]*)\)")


def strip_inline_code(line: str) -> str:
    """Replace inline-code spans with spaces so column positions are
    preserved but their contents are not scanned."""
    out = []
    in_code = False
    for ch in line:
        if ch == "`":
            in_code = not in_code
            out.append(" ")
        elif in_code:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def classify(inside: str):
    """Inspect the content between '(' and ')' of an image reference.

    Returns (problem, displayed_url) where problem is one of:
      None        -> the reference is OK
      'whitespace'-> URL contains a space and what follows is not a
                     properly quoted title
      'tab'       -> URL contains a literal tab (always invalid)
    """
    if "\t" in inside:
        # A tab is never legal inside an image URL or its title boundary.
        # Report only the URL portion (text up to first whitespace).
        url_part = inside.split(None, 1)[0] if inside.strip() else inside
        return ("tab", inside)
    stripped = inside.strip()
    if not stripped:
        return (None, inside)
    if " " not in stripped:
        return (None, stripped)
    # There is a space. Split into URL and remainder.
    url, _, rest = stripped.partition(" ")
    rest = rest.lstrip()
    # Valid title: starts with " or ' or ( and ends with the matching
    # closer. We accept any content beginning with a quote as "looks
    # like a title" — the renderer will validate the rest.
    if rest.startswith(('"', "'", "(")):
        return (None, url)
    return ("whitespace", stripped)


def scan(text: str):
    in_fence = False
    findings = []
    for i, raw in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scrubbed = strip_inline_code(raw)
        for m in IMAGE_RE.finditer(scrubbed):
            inside = m.group(2)
            problem, shown = classify(inside)
            if problem is None:
                continue
            findings.append((i, m.start(), problem, shown))
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    findings = scan(text)
    for line, col, problem, shown in findings:
        if problem == "tab":
            # Render the tab visibly in the message.
            shown_repr = shown.replace("\t", "\\t")
            print(f"{argv[1]}:{line}:{col+1}: image URL contains tab: {shown_repr!r}")
        else:
            print(f"{argv[1]}:{line}:{col+1}: image URL contains whitespace: {shown!r}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

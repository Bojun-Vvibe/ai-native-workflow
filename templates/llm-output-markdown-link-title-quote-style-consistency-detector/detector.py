#!/usr/bin/env python3
"""
llm-output-markdown-link-title-quote-style-consistency-detector

Pure-stdlib detector for the LLM markdown failure mode where inline
link/image titles use inconsistent quote-wrap styles within one
document. CommonMark allows three title delimiters:

    [text](url "double-quoted title")
    [text](url 'single-quoted title')
    [text](url (paren-wrapped title))

All three render identically. Mixing them inside one doc:

  - breaks markdownlint MD040 / link-title-style rules,
  - makes the raw source un-greppable for "every link with a title",
  - confuses auto-formatters that normalize to one style and inflate
    the diff.

Findings are emitted as one JSON object per line on stdout, sorted by
(offset, kind) for byte-identical re-runs. Exit code is 1 if any
finding was emitted, else 0.

Finding kinds:
  - mixed_link_title_quote_style: document uses more than one of
    {double, single, paren}. Reported once per minority-style title
    occurrence.
  - empty_link_title: title delimiters are present but empty
    (`""`, `''`, `()`). These render as no-title and are almost
    always an LLM mistake.
  - unbalanced_paren_title: paren-style title contains an unescaped
    inner paren that breaks CommonMark parsing.

Out of scope:
  - whether the link target URL is reachable,
  - reference-style links `[text][ref]` — different surface,
  - autolinks `<https://...>` — they cannot have titles.

Usage:
  python3 detector.py path/to/file.md
  cat file.md | python3 detector.py -
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple


FENCE_RE = re.compile(r"^(?P<f>`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`+")

# Inline link/image with optional title.
# Group 1: `!` if image else empty
# Group 2: link text
# Group 3: URL (non-paren or angle-bracketed)
# Group 4: title delimiter+content+closer (optional)
#
# CommonMark grammar is forgiving; we deliberately keep this pragmatic:
# we look for `](` then capture until the closing `)` accounting for a
# trailing optional title.
LINK_OPEN_RE = re.compile(r"(?P<bang>!?)\[(?P<text>(?:[^\[\]\\]|\\.)*?)\]\(")


def _mask_code_blocks_and_inline(text: str) -> str:
    """
    Replace fenced code block content and inline code spans with the
    same number of spaces (preserving line/column offsets) so the link
    scanner doesn't trip on `[x](y "z")` patterns inside backticks.
    """
    lines = text.splitlines(keepends=True)
    in_fence = False
    fence_char: Optional[str] = None
    fence_len = 0
    out_lines = []
    for line in lines:
        m = FENCE_RE.match(line)
        if not in_fence and m:
            f = m.group("f")
            fence_char = f[0]
            fence_len = len(f)
            in_fence = True
            out_lines.append(" " * (len(line) - 1) + ("\n" if line.endswith("\n") else ""))
            continue
        if in_fence:
            stripped = line.strip()
            if (
                fence_char is not None
                and stripped.startswith(fence_char * fence_len)
                and set(stripped) == {fence_char}
            ):
                in_fence = False
                fence_char = None
                fence_len = 0
            out_lines.append(" " * (len(line) - 1) + ("\n" if line.endswith("\n") else ""))
            continue
        # mask inline backtick spans on this line
        masked = _mask_inline_code(line)
        out_lines.append(masked)
    return "".join(out_lines)


def _mask_inline_code(line: str) -> str:
    out = list(line)
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            # count run length
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = j - i
            # find matching closing run of same length
            k = j
            while k < n:
                if line[k] == "`":
                    m = k
                    while m < n and line[m] == "`":
                        m += 1
                    if m - k == run:
                        # mask between j..m
                        for x in range(j, m):
                            out[x] = " "
                        i = m
                        break
                    k = m
                else:
                    k += 1
            else:
                break
        else:
            i += 1
    return "".join(out)


@dataclass(frozen=True)
class Finding:
    kind: str
    offset: int
    line: int
    col: int
    quote_style: str  # "double" | "single" | "paren" | "none"
    title: str
    note: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)


@dataclass
class TitleHit:
    offset: int
    line: int
    col: int
    quote_style: str
    title: str
    inner_paren_balanced: bool


def _line_col(text: str, offset: int) -> Tuple[int, int]:
    """1-indexed line, 1-indexed col."""
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl  # if last_nl==-1 -> col = offset+1
    return line, col


def _find_link_destinations(masked: str) -> List[TitleHit]:
    """
    Scan masked text for inline link `]( ... )` blocks and try to
    extract the optional title with its quote style. Returns one
    TitleHit per link that *has* a title (links without a title are
    skipped — there's nothing to be inconsistent about).
    """
    hits: List[TitleHit] = []
    for m in LINK_OPEN_RE.finditer(masked):
        start = m.end()  # position right after `](`
        # walk forward to find the closing `)` of the link, respecting
        # a possible inner balanced angle-bracketed URL or title.
        i = start
        n = len(masked)
        # Skip URL part: either <...> or run of non-whitespace (no parens)
        if i < n and masked[i] == "<":
            j = masked.find(">", i + 1)
            if j == -1:
                continue
            i = j + 1
        else:
            # URL: until whitespace or `)` or end
            j = i
            depth = 0
            while j < n:
                c = masked[j]
                if c == "(":
                    depth += 1
                    j += 1
                    continue
                if c == ")":
                    if depth == 0:
                        break
                    depth -= 1
                    j += 1
                    continue
                if c.isspace():
                    break
                j += 1
            i = j
        # skip whitespace
        while i < n and masked[i] in " \t":
            i += 1
        if i >= n:
            continue
        if masked[i] == ")":
            # no title
            continue
        # title delimiter
        ch = masked[i]
        if ch not in ('"', "'", "("):
            continue
        title_start_offset = i
        if ch == "(":
            closer = ")"
        else:
            closer = ch
        # find closer
        j = i + 1
        title_chars: List[str] = []
        balanced = True
        if ch == "(":
            depth = 1
            while j < n:
                c = masked[j]
                if c == "\\" and j + 1 < n:
                    title_chars.append(masked[j + 1])
                    j += 2
                    continue
                if c == "(":
                    depth += 1
                    title_chars.append(c)
                    j += 1
                    continue
                if c == ")":
                    depth -= 1
                    if depth == 0:
                        break
                    title_chars.append(c)
                    j += 1
                    continue
                if c == "\n":
                    j += 1
                    title_chars.append(c)
                    continue
                title_chars.append(c)
                j += 1
            if depth != 0:
                balanced = False
        else:
            while j < n:
                c = masked[j]
                if c == "\\" and j + 1 < n:
                    title_chars.append(masked[j + 1])
                    j += 2
                    continue
                if c == closer:
                    break
                title_chars.append(c)
                j += 1
            else:
                continue
            # need closing `)` after the title closer
        if j >= n:
            continue
        # confirm we can reach `)` after the title block
        k = j + 1
        while k < n and masked[k] in " \t":
            k += 1
        if k >= n or masked[k] != ")":
            # not a well-formed link — skip
            continue
        style_map = {'"': "double", "'": "single", "(": "paren"}
        quote_style = style_map[ch]
        title_text = "".join(title_chars)
        line, col = _line_col(masked, title_start_offset)
        hits.append(
            TitleHit(
                offset=title_start_offset,
                line=line,
                col=col,
                quote_style=quote_style,
                title=title_text,
                inner_paren_balanced=balanced,
            )
        )
    return hits


def detect(text: str) -> List[Finding]:
    masked = _mask_code_blocks_and_inline(text)
    hits = _find_link_destinations(masked)
    findings: List[Finding] = []

    # empty titles
    for h in hits:
        if h.title.strip() == "":
            findings.append(
                Finding(
                    kind="empty_link_title",
                    offset=h.offset,
                    line=h.line,
                    col=h.col,
                    quote_style=h.quote_style,
                    title="",
                    note=(
                        "link title delimiters are present but empty; "
                        "drop the title or fill it in"
                    ),
                )
            )

    # unbalanced paren titles
    for h in hits:
        if h.quote_style == "paren" and not h.inner_paren_balanced:
            findings.append(
                Finding(
                    kind="unbalanced_paren_title",
                    offset=h.offset,
                    line=h.line,
                    col=h.col,
                    quote_style="paren",
                    title=h.title,
                    note=(
                        "paren-style link title has unescaped/unbalanced "
                        "inner parenthesis; switch to a quoted style or "
                        "escape the inner paren"
                    ),
                )
            )

    # style mix
    style_buckets = {"double": [], "single": [], "paren": []}
    for h in hits:
        style_buckets[h.quote_style].append(h)
    used_styles = [s for s, v in style_buckets.items() if v]
    if len(used_styles) >= 2:
        # majority = bucket with the most hits; tie -> double > single > paren
        priority = {"double": 0, "single": 1, "paren": 2}
        majority_style = max(
            used_styles, key=lambda s: (len(style_buckets[s]), -priority[s])
        )
        for s in used_styles:
            if s == majority_style:
                continue
            for h in style_buckets[s]:
                findings.append(
                    Finding(
                        kind="mixed_link_title_quote_style",
                        offset=h.offset,
                        line=h.line,
                        col=h.col,
                        quote_style=h.quote_style,
                        title=h.title,
                        note=(
                            f"document mixes link-title quote styles "
                            f"({sorted(used_styles)}); majority style is "
                            f"'{majority_style}'"
                        ),
                    )
                )

    findings.sort(key=lambda f: (f.offset, f.kind))
    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py <path|->", file=sys.stderr)
        return 2
    src = argv[1]
    if src == "-":
        text = sys.stdin.read()
    else:
        with open(src, "r", encoding="utf-8") as f:
            text = f.read()
    findings = detect(text)
    for f in findings:
        print(f.to_json())
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

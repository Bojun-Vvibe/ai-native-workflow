"""llm-output-fence-extractor — stdlib-only reference.

Robustly extract fenced code blocks from LLM markdown output.

Real-world LLM markdown is messy:
  * Mixed fence widths: ``` and ````
  * Inner fences (e.g. a ``` block that contains a ```` block).
  * Language tags with whitespace, attributes, no tag at all, or tags
    like "python {.numberLines}" that should be normalized to "python".
  * Unterminated final fence (model truncated mid-block).
  * Fences indented under a list item.
  * `~~~` style fences (CommonMark also allows tildes).

This module returns a stable, structured list of CodeBlock entries with
exact source spans and a `terminated: bool` flag so downstream callers
can treat truncated blocks differently from clean ones.

API:
    extract_blocks(text, *, only_lang=None, normalize_lang=True) -> list[CodeBlock]
    extract_first(text, lang=None) -> Optional[CodeBlock]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class CodeBlock:
    lang: str           # normalized language tag, "" if absent
    info: str           # full info string, e.g. "python {.numberLines}"
    body: str           # block contents WITHOUT trailing newline normalization
    fence_char: str     # '`' or '~'
    fence_len: int      # number of fence chars (>=3)
    indent: str         # leading whitespace stripped from each body line (for indented fences)
    start_line: int     # 1-based, line of opening fence
    end_line: int       # 1-based, line of closing fence (or last line if unterminated)
    terminated: bool    # True if a matching closing fence was found


_OPEN_RE = re.compile(
    r"""^(?P<indent>[ \t]{0,3})           # CommonMark allows up to 3 spaces of indent
        (?P<fence>(?P<char>`|~)(?P=char){2,})   # 3+ of the same fence char
        [ \t]*
        (?P<info>[^\n]*?)
        [ \t]*$
    """,
    re.VERBOSE,
)


def _normalize_lang(info: str) -> str:
    """Pull the first whitespace-delimited token, strip braces / attrs."""
    if not info:
        return ""
    tok = info.strip().split()[0] if info.strip() else ""
    # Drop attribute braces: "python{.numberLines}" -> "python"
    tok = tok.split("{", 1)[0]
    # Drop trailing punctuation that sometimes leaks: "python," "python:"
    tok = tok.rstrip(",;:")
    return tok.lower()


def extract_blocks(
    text: str,
    *,
    only_lang: Optional[str] = None,
    normalize_lang: bool = True,
) -> List[CodeBlock]:
    """Return all fenced blocks in document order.

    `only_lang` filters by normalized lang (case-insensitive). Pass "" to
    select blocks with no language tag.
    """
    lines = text.splitlines()
    blocks: List[CodeBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        m = _OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        open_indent = m.group("indent")
        open_fence = m.group("fence")
        open_char = m.group("char")
        open_len = len(open_fence)
        info = m.group("info")
        start_line = i + 1
        i += 1
        body_lines: List[str] = []
        terminated = False
        end_line = start_line
        while i < n:
            line = lines[i]
            # Closing fence: same char, length >= open_len, only whitespace after.
            stripped = line.lstrip(" \t")
            leading = line[: len(line) - len(stripped)]
            if (
                len(leading) <= 3
                and stripped.startswith(open_char)
                and re.match(rf"^{re.escape(open_char)}{{{open_len},}}[ \t]*$", stripped)
            ):
                terminated = True
                end_line = i + 1
                i += 1
                break
            # Strip the opening indent (CommonMark behavior) when present.
            if open_indent and line.startswith(open_indent):
                body_lines.append(line[len(open_indent):])
            else:
                body_lines.append(line)
            i += 1
        else:
            # Reached EOF without close.
            end_line = n
        body = "\n".join(body_lines)
        lang = _normalize_lang(info) if normalize_lang else (info.strip().split()[0] if info.strip() else "")
        if only_lang is not None and lang != only_lang.lower():
            continue
        blocks.append(
            CodeBlock(
                lang=lang,
                info=info.strip(),
                body=body,
                fence_char=open_char,
                fence_len=open_len,
                indent=open_indent,
                start_line=start_line,
                end_line=end_line,
                terminated=terminated,
            )
        )
    return blocks


def extract_first(text: str, lang: Optional[str] = None) -> Optional[CodeBlock]:
    blocks = extract_blocks(text, only_lang=lang)
    return blocks[0] if blocks else None

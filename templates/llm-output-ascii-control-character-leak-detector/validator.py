"""
llm-output-ascii-control-character-leak-detector
================================================

Pure-stdlib detector for ASCII C0 control characters (U+0000..U+001F)
and DEL (U+007F) that leak into LLM output where they should not
appear.

This is the *7-bit* sibling of `llm-output-zero-width-character-detector`
(which targets multi-byte invisible Unicode codepoints). The two
problem classes are orthogonal: a NUL byte from a tokenizer hiccup is a
distinctly different bug from a U+200B from a copy-pasted training
sample, and conflating them in one report makes triage harder.

Permitted by default: ``\\t`` (HT, U+0009), ``\\n`` (LF, U+000A),
``\\r`` (CR, U+000D). Everything else in C0 + DEL is reported.

Pure function over a string. No I/O. Stdlib-only.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable


# --- finding kinds (stable strings; downstream pipelines key on these) -----

KIND_NUL = "nul_byte"                  # U+0000  - high-severity
KIND_BELL = "bell"                     # U+0007  - terminal nuisance
KIND_BACKSPACE = "backspace"           # U+0008  - corrupts diffs
KIND_VERTICAL_TAB = "vertical_tab"     # U+000B  - whitespace masquerading as LF
KIND_FORM_FEED = "form_feed"           # U+000C  - same
KIND_ESCAPE = "escape"                 # U+001B  - ANSI escape lead-in (high-severity)
KIND_DEL = "del"                       # U+007F  - non-printable, dangerous in regex
KIND_OTHER_C0 = "other_c0"             # everything else 0x00..0x1F not above

# Codepoints we explicitly allow by default.
DEFAULT_ALLOWED = frozenset({0x09, 0x0A, 0x0D})


@dataclass(frozen=True)
class Finding:
    offset: int          # zero-based char index into the source text
    line_no: int         # 1-based
    column: int          # 1-based
    codepoint: int       # ord(char)
    char_name: str       # unicodedata name or "<control-XX>"
    kind: str            # one of the KIND_* constants
    in_code: bool        # True if inside a fenced or inline code span


# --- helpers ---------------------------------------------------------------

def _classify(cp: int) -> str:
    if cp == 0x00:
        return KIND_NUL
    if cp == 0x07:
        return KIND_BELL
    if cp == 0x08:
        return KIND_BACKSPACE
    if cp == 0x0B:
        return KIND_VERTICAL_TAB
    if cp == 0x0C:
        return KIND_FORM_FEED
    if cp == 0x1B:
        return KIND_ESCAPE
    if cp == 0x7F:
        return KIND_DEL
    return KIND_OTHER_C0


def _char_name(cp: int) -> str:
    try:
        n = unicodedata.name(chr(cp))
        if n:
            return n
    except ValueError:
        pass
    return f"<control-{cp:02X}>"


def _build_in_code_mask(text: str) -> list[bool]:
    """
    Mark each character offset as `in_code=True` if it lies inside a
    Markdown fenced code block (``` or ~~~) or an inline backtick run.

    The fence-awareness convention matches the rest of the
    llm-output-* detector family so a single CI step can union reports
    without column drift.
    """
    n = len(text)
    mask = [False] * n
    i = 0
    in_fence = False
    fence_marker = ""
    line_start = 0
    while i < n:
        # detect line start to look for fenced markers
        if i == line_start:
            # skip leading spaces (up to 3) per CommonMark
            j = i
            while j < n and j - i < 4 and text[j] == " ":
                j += 1
            if j < n and (text[j] == "`" or text[j] == "~"):
                ch = text[j]
                k = j
                while k < n and text[k] == ch:
                    k += 1
                run = k - j
                if run >= 3:
                    if not in_fence:
                        in_fence = True
                        fence_marker = ch * run
                        # mark the fence line itself as in_code so a control
                        # char on the marker line is still flagged but tagged
                        eol = text.find("\n", k)
                        eol = n if eol == -1 else eol
                        for p in range(i, eol):
                            mask[p] = True
                        i = eol
                        line_start = eol + 1 if eol < n else n
                        if i < n and text[i] == "\n":
                            i += 1
                        continue
                    else:
                        # closing fence must be same char and >= opening run
                        if ch == fence_marker[0] and run >= len(fence_marker):
                            in_fence = False
                            fence_marker = ""
                            eol = text.find("\n", k)
                            eol = n if eol == -1 else eol
                            for p in range(i, eol):
                                mask[p] = True
                            i = eol
                            line_start = eol + 1 if eol < n else n
                            if i < n and text[i] == "\n":
                                i += 1
                            continue

        if in_fence:
            mask[i] = True
            if text[i] == "\n":
                line_start = i + 1
            i += 1
            continue

        # inline backtick run
        if text[i] == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            run = j - i
            close = text.find("`" * run, j)
            if close != -1:
                # everything between i and close+run is in inline code
                end = close + run
                for p in range(i, end):
                    mask[p] = True
                i = end
                continue
            # unmatched backticks: treat as literal, not code
            i = j
            continue

        if text[i] == "\n":
            line_start = i + 1
        i += 1
    return mask


def _line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - (last_nl + 1) + 1
    return line, col


# --- public API ------------------------------------------------------------

def detect_controls(
    text: str,
    *,
    allowlist: Iterable[int] = DEFAULT_ALLOWED,
    suppress_in_code: bool = False,
) -> list[Finding]:
    """
    Scan ``text`` for ASCII C0 / DEL leaks.

    Args:
        text: source string.
        allowlist: codepoints to ignore. Defaults to {HT, LF, CR}.
        suppress_in_code: when True, findings inside fenced or inline
            code spans are dropped. Default False — production prose
            pipelines should usually leave it False.

    Returns: list[Finding] sorted by (offset, kind). Stable across
    re-runs over byte-identical input.
    """
    allowed = frozenset(allowlist)
    mask = _build_in_code_mask(text)
    findings: list[Finding] = []
    for off, ch in enumerate(text):
        cp = ord(ch)
        if cp > 0x1F and cp != 0x7F:
            continue
        if cp in allowed:
            continue
        in_code = mask[off] if off < len(mask) else False
        if suppress_in_code and in_code:
            continue
        line, col = _line_col(text, off)
        findings.append(
            Finding(
                offset=off,
                line_no=line,
                column=col,
                codepoint=cp,
                char_name=_char_name(cp),
                kind=_classify(cp),
                in_code=in_code,
            )
        )
    findings.sort(key=lambda f: (f.offset, f.kind))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no ASCII control characters found."
    lines = [f"FOUND {len(findings)} control character(s):"]
    for f in findings:
        tag = " [in_code]" if f.in_code else ""
        lines.append(
            f"  line {f.line_no} col {f.column} offset {f.offset}: "
            f"U+{f.codepoint:04X} {f.char_name} kind={f.kind}{tag}"
        )
    return "\n".join(lines)

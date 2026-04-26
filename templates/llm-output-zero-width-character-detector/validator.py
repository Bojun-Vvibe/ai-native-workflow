"""Zero-width and invisible-control character detector for LLM output.

Pure stdlib. Scans LLM-generated text for invisible Unicode characters
that render as nothing but corrupt downstream processing: tokenizers
split on them, search/grep misses literal-string matches, diff tools
show identical-looking lines that are not byte-equal, and copy-paste
from the rendered output silently propagates the invisibles into
source code (where they can break compilers, test assertions, and
config parsers).

Detected character classes (each its own finding kind so the operator
can decide which classes are tolerable for their pipeline):

  - ``zero_width_space``   U+200B  ZERO WIDTH SPACE
  - ``zero_width_non_joiner`` U+200C  ZERO WIDTH NON-JOINER
  - ``zero_width_joiner``  U+200D  ZERO WIDTH JOINER
  - ``word_joiner``        U+2060  WORD JOINER
  - ``bom_or_zwnbsp``      U+FEFF  BYTE ORDER MARK / ZWNBSP
  - ``soft_hyphen``        U+00AD  SOFT HYPHEN
  - ``bidi_control``       U+202A..U+202E, U+2066..U+2069  (LRE, RLE,
                              PDF, LRO, RLO, LRI, RLI, FSI, PDI)
                              — the Trojan-Source class
  - ``invisible_separator``    U+2063  INVISIBLE SEPARATOR
  - ``invisible_times``        U+2062  INVISIBLE TIMES
  - ``function_application``   U+2061  FUNCTION APPLICATION
  - ``mongolian_vowel_separator`` U+180E
  - ``hangul_filler``      U+115F, U+1160, U+3164, U+FFA0
  - ``tag_character``      U+E0000..U+E007F  (the emoji-tag block,
                              also the ASCII Smuggler steganography
                              channel)

Every finding carries:

  - ``offset``    0-based char index into the original string
  - ``line_no``   1-based line number (newline-counted)
  - ``column``    1-based column inside that line
  - ``codepoint`` the U+XXXX form for the report
  - ``char_name`` the Unicode name (best-effort via ``unicodedata``;
                  falls back to ``"<unnamed>"`` when the character has
                  no name in the ICU database shipped with the
                  interpreter)
  - ``kind``      the finding-kind string above
  - ``in_code``   True if the byte sits inside a fenced code block
                  (` ``` ` / ``~~~``) or an inline ``code`` span — the
                  caller often wants to suppress code-span findings
                  because a code sample may legitimately demonstrate
                  invisible chars

Findings are sorted by ``(offset, kind)`` so byte-identical re-runs
make diff-on-the-output a valid CI signal.

Composes with:

  - ``llm-output-trailing-whitespace-and-tab-detector`` — orthogonal
    invisible-byte hygiene axis (visible-but-trailing whitespace vs
    truly-invisible codepoints); same ``Finding`` shape and stable
    sort, so a single CI step can union both reports.
  - ``llm-output-emphasis-marker-consistency-validator`` and the rest
    of the Markdown-hygiene family — same fence-awareness convention.
  - ``agent-output-validation`` — feed ``(kind, offset)`` into the
    repair prompt for a one-turn fix (``"strip the U+200B at column
    14 of line 3"``).
  - ``structured-error-taxonomy`` — ``bidi_control`` and
    ``tag_character`` are ``do_not_retry / attribution=infrastructure``
    (Trojan-Source / ASCII-Smuggler classes; the model is being fed
    or asked to produce hostile bytes and the right action is to
    block the request, not retry it). The other kinds are
    ``do_not_retry / attribution=model``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable


# Codepoint -> kind. Single chars listed individually so the table
# is greppable; ranges expanded at module load.
_SINGLES: dict[int, str] = {
    0x200B: "zero_width_space",
    0x200C: "zero_width_non_joiner",
    0x200D: "zero_width_joiner",
    0x2060: "word_joiner",
    0xFEFF: "bom_or_zwnbsp",
    0x00AD: "soft_hyphen",
    0x2063: "invisible_separator",
    0x2062: "invisible_times",
    0x2061: "function_application",
    0x180E: "mongolian_vowel_separator",
    0x115F: "hangul_filler",
    0x1160: "hangul_filler",
    0x3164: "hangul_filler",
    0xFFA0: "hangul_filler",
}

# Bidi controls: the Trojan-Source class. These are the high-severity
# kind because they can re-order surrounding code at render time
# without changing the byte stream the compiler sees.
for cp in range(0x202A, 0x202F):  # LRE, RLE, PDF, LRO, RLO
    _SINGLES[cp] = "bidi_control"
for cp in range(0x2066, 0x206A):  # LRI, RLI, FSI, PDI
    _SINGLES[cp] = "bidi_control"

# Tag characters: U+E0000..U+E007F. Used by emoji flags legitimately,
# but also by the "ASCII Smuggler" steganography pattern that hides
# arbitrary text inside what looks like a single emoji or a blank
# span. Flagged unconditionally; caller can suppress via allowlist.
_TAG_RANGE = (0xE0000, 0xE007F)


@dataclass(frozen=True)
class Finding:
    offset: int
    line_no: int
    column: int
    codepoint: str
    char_name: str
    kind: str
    in_code: bool


def _classify(cp: int) -> str | None:
    if cp in _SINGLES:
        return _SINGLES[cp]
    if _TAG_RANGE[0] <= cp <= _TAG_RANGE[1]:
        return "tag_character"
    return None


def _name(ch: str) -> str:
    try:
        return unicodedata.name(ch)
    except ValueError:
        return "<unnamed>"


def _build_code_mask(text: str) -> list[bool]:
    """Return a per-char bitmap: True where the char is inside a
    fenced code block (``` / ~~~) or an inline `code` span.

    The fence parser is intentionally minimal — it matches the
    convention used across the templates/llm-output-* family
    (CommonMark-aligned: opener is a run of >=3 of the same char
    with indent <=3 spaces; closer must be the same char with run
    length >= opener's). Inline code spans use single-backtick
    matching on a per-line basis (a fenced block takes precedence).
    """
    n = len(text)
    mask = [False] * n
    i = 0
    in_fence = False
    fence_char = ""
    fence_run = 0

    # Walk line-by-line so column / line counters stay simple.
    while i < n:
        # Find end of this line.
        line_end = text.find("\n", i)
        if line_end == -1:
            line_end = n
        line = text[i:line_end]

        # Check for a fence opener / closer at the line head.
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent <= 3 and stripped[:3] in ("```", "~~~"):
            ch = stripped[0]
            run = 0
            for c in stripped:
                if c == ch:
                    run += 1
                else:
                    break
            if not in_fence:
                in_fence = True
                fence_char = ch
                fence_run = run
                # Mark the fence line itself as in_code.
                for j in range(i, line_end):
                    mask[j] = True
            else:
                # Closer must match char and have run length >= opener.
                if ch == fence_char and run >= fence_run and stripped[run:].strip() == "":
                    for j in range(i, line_end):
                        mask[j] = True
                    in_fence = False
                    fence_char = ""
                    fence_run = 0
                else:
                    # Inside fence — body line.
                    for j in range(i, line_end):
                        mask[j] = True
        elif in_fence:
            for j in range(i, line_end):
                mask[j] = True
        else:
            # Inline-code spans: scan for backtick-delimited runs.
            j = i
            while j < line_end:
                if line[j - i] == "`":
                    # Find run length of opener.
                    k = j
                    while k < line_end and line[k - i] == "`":
                        k += 1
                    run_len = k - j
                    # Look for matching closer of same length.
                    m = k
                    while m < line_end:
                        if line[m - i] == "`":
                            mk = m
                            while mk < line_end and line[mk - i] == "`":
                                mk += 1
                            if mk - m == run_len:
                                # Mask from j (opener) through mk-1 (closer).
                                for q in range(j, mk):
                                    mask[q] = True
                                j = mk
                                break
                            else:
                                m = mk
                        else:
                            m += 1
                    else:
                        # No closer on this line — leave the backticks alone.
                        j = line_end
                        break
                    # j was set to mk above; loop continues.
                    continue
                j += 1

        # Advance past the newline.
        i = line_end + 1
    return mask


def detect_invisibles(
    text: str,
    *,
    allowlist: Iterable[int] = (),
    suppress_in_code: bool = False,
) -> list[Finding]:
    """Scan ``text`` for invisible / control codepoints.

    ``allowlist`` is an iterable of codepoint integers to skip
    entirely (e.g. project deliberately uses ZWJ in its emoji
    sequences and accepts the risk).

    ``suppress_in_code=True`` drops findings that fall inside a
    fenced code block or an inline code span — the right setting for
    docs whose code samples may legitimately demonstrate invisible
    chars. Default is False: report everything and let the caller
    filter.
    """
    allow = set(allowlist)
    code_mask = _build_code_mask(text) if suppress_in_code or True else None
    # Always build the mask so every Finding can carry in_code; the
    # ``or True`` above just keeps the structure obvious.

    findings: list[Finding] = []
    line_no = 1
    line_start = 0
    for offset, ch in enumerate(text):
        if ch == "\n":
            line_no += 1
            line_start = offset + 1
            continue
        cp = ord(ch)
        if cp in allow:
            continue
        kind = _classify(cp)
        if kind is None:
            continue
        in_code = code_mask[offset] if code_mask is not None else False
        if suppress_in_code and in_code:
            continue
        findings.append(
            Finding(
                offset=offset,
                line_no=line_no,
                column=offset - line_start + 1,
                codepoint=f"U+{cp:04X}",
                char_name=_name(ch),
                kind=kind,
                in_code=in_code,
            )
        )

    findings.sort(key=lambda f: (f.offset, f.kind))
    return findings


def format_report(findings: list[Finding]) -> str:
    """Render findings as a stable, line-oriented report."""
    if not findings:
        return "OK: no invisible characters found.\n"
    lines = [f"FOUND {len(findings)} invisible character(s):"]
    for f in findings:
        flag = " [in_code]" if f.in_code else ""
        lines.append(
            f"  line {f.line_no} col {f.column} offset {f.offset}: "
            f"{f.codepoint} {f.char_name} kind={f.kind}{flag}"
        )
    return "\n".join(lines) + "\n"

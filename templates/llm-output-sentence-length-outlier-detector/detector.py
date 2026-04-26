"""Pure-stdlib detector for sentence-length outliers in an LLM prose
output blob.

A normal prose paragraph from a well-tuned model has sentences
clustered in the 8-25 word range. The two failure modes that this
template catches are the ones that a downstream grader / TTS engine /
human reader will trip on:

  - `long_sentence` — a sentence whose word count exceeds
    `max_words` (default 40). LLMs run away from periods when they
    are streaming a list-like clarification ("we saw A, and B,
    and C, and also D, which means..."). Sentences over 40 words
    are read 30-40% slower and are the #1 source of "wait, what
    was the subject?" misreads in LLM-generated docs.
  - `short_sentence` — a sentence whose word count is below
    `min_words` (default 3). Single-word "Yes." and "Done." are
    fine in dialog but inside a paragraph of prose they almost
    always indicate a botched stream join (a fragment got split
    off from the previous sentence by an erroneous period).
  - `outlier_sentence` — a sentence whose word count is more than
    `outlier_factor` (default 3.0) standard deviations from the
    paragraph's own mean. This catches the "buried-clause"
    failure: a 60-word sentence in a paragraph of otherwise
    12-word sentences IS the bug, even if 60 < `max_words` would
    have let it pass an absolute check. Only fires for paragraphs
    with `>= 3` sentences (need a real sample to compute a useful
    stddev). The same sentence may fire BOTH `long_sentence` AND
    `outlier_sentence` — they are reported as separate findings
    because they suggest different fixes (split vs. condense).

Sentence segmentation is intentionally minimal: split on `.`, `!`,
`?` followed by whitespace or EOF, with a small abbreviation skip-list
(`Mr.`, `Mrs.`, `Ms.`, `Dr.`, `St.`, `vs.`, `e.g.`, `i.e.`, `etc.`,
`Inc.`, `Ltd.`, `No.`) so "Dr. Smith arrived." is one sentence, not
two. Decimal numbers (`3.14`) are skipped (a `.` between two digits
does not end a sentence). Code spans (`` `code` ``) and fenced code
blocks (` ``` `) are excluded entirely from sentence accounting —
their `.` and `?` are syntax, not punctuation.

Pure: input is `str`, no I/O, no third-party deps, no NLP library.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    kind: str
    sentence_index: int  # 1-based, across the entire blob (post-fence-strip)
    line_number: int  # 1-based; line where the sentence STARTS
    word_count: int
    detail: str


_KINDS = ("short_sentence", "long_sentence", "outlier_sentence")

_ABBREVIATIONS = frozenset(
    {
        "Mr.",
        "Mrs.",
        "Ms.",
        "Dr.",
        "St.",
        "vs.",
        "e.g.",
        "i.e.",
        "etc.",
        "Inc.",
        "Ltd.",
        "No.",
    }
)


def _strip_code(text: str) -> str:
    """Replace fenced-code blocks and inline-code spans with spaces of
    equal length so line numbers and column offsets are preserved."""
    out_chars = []
    i = 0
    n = len(text)
    in_fence = False
    in_inline = False
    while i < n:
        # fence detection: ``` at start of (logical) line
        if not in_inline and text[i : i + 3] == "```" and (i == 0 or text[i - 1] == "\n"):
            in_fence = not in_fence
            # blank out the ``` themselves but keep newlines intact
            for _ in range(3):
                out_chars.append(" ")
            i += 3
            continue
        ch = text[i]
        if in_fence:
            out_chars.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if ch == "`":
            in_inline = not in_inline
            out_chars.append(" ")
            i += 1
            continue
        if in_inline:
            out_chars.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        out_chars.append(ch)
        i += 1
    return "".join(out_chars)


def _is_decimal_dot(text: str, i: int) -> bool:
    """Is text[i] == '.' a decimal-number dot (digit before AND after)?"""
    if i <= 0 or i >= len(text) - 1:
        return False
    return text[i - 1].isdigit() and text[i + 1].isdigit()


def _ends_with_abbreviation(buf: str) -> bool:
    """Does the trailing token of `buf` (ending at the last char,
    which must be `.`) match a known abbreviation?"""
    # walk backward from the end (which is `.`) to a whitespace boundary
    if not buf or buf[-1] != ".":
        return False
    j = len(buf) - 2
    while j >= 0 and not buf[j].isspace():
        j -= 1
    token = buf[j + 1 :]
    return token in _ABBREVIATIONS


def _split_sentences(text: str) -> List[Tuple[str, int]]:
    """Split `text` into (sentence_text, start_line_1based) tuples.

    Splits on `.`, `!`, `?` followed by whitespace or EOF, with the
    abbreviation and decimal-dot skips described in the module docstring.
    """
    sentences: List[Tuple[str, int]] = []
    n = len(text)
    if n == 0:
        return sentences

    line_starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(idx + 1)

    def line_of(pos: int) -> int:
        # binary-search-ish but lists are short; linear is fine for stdlib clarity
        ln = 1
        for ls in line_starts:
            if ls <= pos:
                ln = line_starts.index(ls) + 1
            else:
                break
        return ln

    start = 0
    i = 0
    while i < n:
        ch = text[i]
        if ch in ".!?":
            # decimal dot? skip
            if ch == "." and _is_decimal_dot(text, i):
                i += 1
                continue
            # is the char after the terminator whitespace or EOF?
            j = i + 1
            # collapse multiple terminators (e.g. "?!", "...") into one boundary
            while j < n and text[j] in ".!?":
                j += 1
            if j == n or text[j].isspace():
                # candidate sentence end at i (or j-1 if collapsed)
                buf = text[start:j]
                # abbreviation skip only matters when terminator is a single `.`
                if (
                    ch == "."
                    and j == i + 1
                    and _ends_with_abbreviation(buf)
                ):
                    i = j
                    continue
                sentence = text[start:j].strip()
                if sentence:
                    # find the first non-whitespace char position from `start`
                    s_pos = start
                    while s_pos < j and text[s_pos].isspace():
                        s_pos += 1
                    sentences.append((sentence, line_of(s_pos)))
                start = j
                i = j
                continue
        i += 1

    # tail: any leftover after the last terminator is a "sentence" too,
    # but only if it contains non-whitespace
    tail = text[start:].strip()
    if tail:
        s_pos = start
        while s_pos < n and text[s_pos].isspace():
            s_pos += 1
        sentences.append((tail, line_of(s_pos)))

    return sentences


def _word_count(sentence: str) -> int:
    # Words = whitespace-separated tokens that contain at least one
    # alphanumeric char. Drops bare punctuation tokens.
    count = 0
    for tok in sentence.split():
        for ch in tok:
            if ch.isalnum():
                count += 1
                break
    return count


def _split_paragraphs_with_sentence_index(
    sentences: List[Tuple[str, int]]
) -> List[List[int]]:
    """Group sentences into paragraphs by line gap (>= 2 line jump).

    Returns a list of paragraphs; each paragraph is a list of
    1-based sentence indices into `sentences`.
    """
    paragraphs: List[List[int]] = []
    current: List[int] = []
    prev_line = None
    for idx, (_text, line) in enumerate(sentences, start=1):
        if prev_line is None or line - prev_line <= 1:
            current.append(idx)
        else:
            if current:
                paragraphs.append(current)
            current = [idx]
        prev_line = line
    if current:
        paragraphs.append(current)
    return paragraphs


def detect_sentence_length_outliers(
    text: str,
    *,
    min_words: int = 3,
    max_words: int = 40,
    outlier_factor: float = 3.0,
) -> List[Finding]:
    """Detect short, long, and statistical-outlier sentences.

    Args:
      text: the LLM output blob to scan.
      min_words: sentences with strictly fewer words fire `short_sentence`.
        Default 3. Set to 1 to allow "Yes." / "Done." style fragments.
      max_words: sentences with strictly more words fire `long_sentence`.
        Default 40. Set higher (e.g. 60) for academic / legal prose.
      outlier_factor: stddev-multiplier threshold for `outlier_sentence`.
        Default 3.0. A sentence whose word count differs from its
        own paragraph's mean by more than `outlier_factor * stddev`
        fires. Only applies to paragraphs with `>= 3` sentences.

    Returns:
      Sorted list of Finding records (stable sort by
      (sentence_index, kind)).
    """
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    for name, val in (("min_words", min_words), ("max_words", max_words)):
        if not isinstance(val, int) or isinstance(val, bool):
            raise ValidationError(f"{name} must be int, got {type(val).__name__}")
        if val < 1:
            raise ValidationError(f"{name} must be >= 1, got {val}")
    if not isinstance(outlier_factor, (int, float)) or isinstance(outlier_factor, bool):
        raise ValidationError("outlier_factor must be a number")
    if outlier_factor <= 0:
        raise ValidationError(f"outlier_factor must be > 0, got {outlier_factor}")
    if min_words > max_words:
        raise ValidationError(
            f"min_words ({min_words}) must be <= max_words ({max_words})"
        )

    findings: List[Finding] = []
    if text == "":
        return findings

    stripped = _strip_code(text)
    sentences = _split_sentences(stripped)
    if not sentences:
        return findings

    word_counts = [_word_count(s) for s, _ in sentences]

    # absolute thresholds
    for idx, (_s, line) in enumerate(sentences, start=1):
        wc = word_counts[idx - 1]
        if wc < min_words:
            findings.append(
                Finding(
                    kind="short_sentence",
                    sentence_index=idx,
                    line_number=line,
                    word_count=wc,
                    detail=f"sentence has {wc} word(s) (min: {min_words})",
                )
            )
        if wc > max_words:
            findings.append(
                Finding(
                    kind="long_sentence",
                    sentence_index=idx,
                    line_number=line,
                    word_count=wc,
                    detail=f"sentence has {wc} word(s) (max: {max_words})",
                )
            )

    # statistical outliers per paragraph
    paragraphs = _split_paragraphs_with_sentence_index(sentences)
    for para in paragraphs:
        if len(para) < 3:
            continue
        counts = [word_counts[i - 1] for i in para]
        mean = sum(counts) / len(counts)
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        stddev = math.sqrt(variance)
        if stddev == 0:
            continue
        for i in para:
            wc = word_counts[i - 1]
            deviation = abs(wc - mean) / stddev
            if deviation > outlier_factor:
                _, line = sentences[i - 1]
                findings.append(
                    Finding(
                        kind="outlier_sentence",
                        sentence_index=i,
                        line_number=line,
                        word_count=wc,
                        detail=(
                            f"sentence has {wc} word(s); paragraph mean="
                            f"{mean:.1f} stddev={stddev:.2f} "
                            f"deviation={deviation:.2f}x (factor: {outlier_factor})"
                        ),
                    )
                )

    findings.sort(
        key=lambda f: (
            f.sentence_index,
            _KINDS.index(f.kind) if f.kind in _KINDS else 99,
        )
    )
    return findings


def format_report(findings: List[Finding]) -> str:
    if not findings:
        return "OK: no sentence-length outliers.\n"
    lines = [f"FOUND {len(findings)} sentence-length finding(s):"]
    for f in findings:
        lines.append(
            f"  [{f.kind}] sentence={f.sentence_index} line={f.line_number} "
            f"words={f.word_count} :: {f.detail}"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_sentence_length_outliers",
    "format_report",
]

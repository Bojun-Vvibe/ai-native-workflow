r"""Consecutive-identical-sentence (stutter) detector for LLM output.

Pure stdlib, no I/O. Detects the LLM failure mode where adjacent
sentences are identical or near-identical — the artifact you see when
an instruction-following model loses sampling momentum and emits the
same idea twice in a row, e.g.:

    The deploy is healthy. The deploy is healthy. We can ship.

Three finding kinds:

  - exact_repeat       two adjacent sentences are byte-identical
                       after whitespace normalization
  - case_repeat        two adjacent sentences are identical except
                       for letter case (still almost certainly a
                       model artifact, never an intentional rhetorical
                       device — anaphora repeats the OPENING of
                       successive clauses, not the entire sentence)
  - near_repeat        two adjacent sentences differ by at most
                       `near_max_edits` token edits (default 1) AND
                       are at least `near_min_tokens` tokens long
                       (default 4) — catches the "the same sentence
                       with one word swapped" case while not flagging
                       trivial fragments like 'Yes.' 'No.'

A "sentence" is a maximal run of non-whitespace text terminated by
`.`, `!`, `?`, or end-of-input. Abbreviations and decimal numbers
are NOT special-cased — the detector is intentionally token-cheap
and works on the segmented stream; the only segmentation rule is
"terminator followed by whitespace OR end-of-input ends a sentence".
A trailing terminator with no following whitespace (e.g. `Mr.X`) is
treated as one sentence; this means a misplaced `Mr.` `Smith` will
be one sentence, not two — which is the correct behavior for stutter
detection (no false positives from "St. Louis" "St. Louis" being
flagged because the word "St." appears twice).

Sentence-internal newlines are collapsed to single spaces before
comparison so a hard-wrapped paragraph and a single-line paragraph
compare equal.

Public API:

    detect_stutter(text: str, *,
                   near_max_edits: int = 1,
                   near_min_tokens: int = 4) -> list[Finding]
    format_report(findings: list[Finding]) -> str

Findings sorted by (offset, kind).

Notes:
  - Sentences inside fenced code blocks are SKIPPED (a code comment
    that legitimately contains "TODO. TODO." should not flag).
  - Block boundaries (paragraph breaks, list-item starts, heading
    starts) reset the "previous sentence" context — a section that
    legitimately reuses a heading-like phrase across two sections is
    not a stutter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised when input is not a `str` or thresholds are out of range."""


@dataclass(frozen=True)
class Finding:
    kind: str
    offset: int           # 0-based byte offset of the SECOND sentence
    sentence_a: str       # the earlier sentence (normalized)
    sentence_b: str       # the later sentence (normalized)
    detail: str


_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# Block-boundary markers that reset the previous-sentence context.
# Matched on the line as a whole.
_BLOCK_RESET_RE = re.compile(
    r"^\s*("
    r"$"                      # blank line
    r"|#{1,6}\s"              # heading
    r"|[-*+]\s"               # bullet
    r"|\d+[.)]\s"             # numbered
    r"|>"                     # blockquote marker
    r"|\|"                    # table row
    r")"
)
# Sentence terminators. We split *after* the terminator so the
# terminator stays on the sentence (useful for case_repeat detection
# where 'Yes.' vs 'Yes!' should NOT be a case_repeat — different
# punctuation = different sentence).
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _normalize(s: str) -> str:
    """Collapse internal whitespace; strip leading/trailing whitespace."""
    return re.sub(r"\s+", " ", s).strip()


def _tokenize(s: str) -> list[str]:
    """Lowercase word tokens; strips terminal punctuation."""
    return re.findall(r"[A-Za-z0-9]+", s.lower())


def _edit_distance_tokens(a: list[str], b: list[str], cap: int) -> int:
    """Levenshtein on token sequences, early-exit at `cap+1`.

    Returns the true distance if it is <= `cap`, else `cap + 1`.
    """
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    # Standard DP, single-row optimization.
    prev = list(range(len(b) + 1))
    for i, ai in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        row_min = cur[0]
        for j, bj in enumerate(b, 1):
            cost = 0 if ai == bj else 1
            cur[j] = min(
                cur[j - 1] + 1,        # insert
                prev[j] + 1,           # delete
                prev[j - 1] + cost,    # substitute
            )
            if cur[j] < row_min:
                row_min = cur[j]
        if row_min > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _segment_with_offsets(block: str, base_offset: int) -> list[tuple[int, str]]:
    """Split `block` into (offset, sentence) pairs.

    `offset` is the byte offset of the sentence's first char *in the
    original text* (i.e. `base_offset` + position-within-block).
    """
    out: list[tuple[int, str]] = []
    cursor = 0
    for piece in _SENT_SPLIT_RE.split(block):
        if not piece.strip():
            cursor += len(piece)
            continue
        # Find the actual offset of the (lstripped) piece inside block.
        idx = block.find(piece, cursor)
        if idx < 0:
            idx = cursor
        out.append((base_offset + idx, _normalize(piece)))
        cursor = idx + len(piece)
    return out


def detect_stutter(
    text: str,
    *,
    near_max_edits: int = 1,
    near_min_tokens: int = 4,
) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(
            f"text must be str, got {type(text).__name__}"
        )
    if near_max_edits < 0:
        raise ValidationError("near_max_edits must be >= 0")
    if near_min_tokens < 1:
        raise ValidationError("near_min_tokens must be >= 1")

    findings: list[Finding] = []
    in_fence = False

    # We walk line-by-line so we can (a) detect fences and (b) reset
    # the previous-sentence context at block boundaries. Within each
    # contiguous prose run we accumulate text and run sentence-level
    # comparison.

    lines = text.split("\n")
    block_lines: list[str] = []
    block_offset = 0  # byte offset of the first char of the current block
    char_cursor = 0   # running byte offset into `text`

    def flush_block(prev_carry: list[tuple[int, str]] | None = None) -> None:
        if not block_lines:
            return
        block_text = "\n".join(block_lines)
        sents = _segment_with_offsets(block_text, block_offset)
        # Compare adjacent sentences within this block (block boundaries
        # already reset context per spec).
        for i in range(1, len(sents)):
            off_a, sa = sents[i - 1]
            off_b, sb = sents[i]
            kind = _classify(
                sa, sb,
                near_max_edits=near_max_edits,
                near_min_tokens=near_min_tokens,
            )
            if kind is not None:
                findings.append(Finding(
                    kind=kind,
                    offset=off_b,
                    sentence_a=sa,
                    sentence_b=sb,
                    detail=_detail_for(kind, sa, sb),
                ))

    for line in lines:
        line_len_with_nl = len(line) + 1  # +1 for the \n we split on
        # Fence toggle (opening OR closing) flushes the current block.
        if _FENCE_RE.match(line):
            flush_block()
            block_lines = []
            block_offset = char_cursor + line_len_with_nl
            in_fence = not in_fence
            char_cursor += line_len_with_nl
            continue
        if in_fence:
            char_cursor += line_len_with_nl
            continue
        # Block reset: blank line, heading, bullet, numbered, blockquote,
        # table row.
        if _BLOCK_RESET_RE.match(line):
            flush_block()
            block_lines = []
            # The reset line itself starts a fresh block at THIS line.
            # (A heading line "# Title." can stutter against the next
            # sentence in its own paragraph if treated as the same block,
            # but we treat the heading as its own one-sentence block —
            # which is correct: "## Stage 1" "Stage 1 begins." should
            # not flag.)
            if line.strip():
                # Treat the line as its own block; flush immediately
                # (single sentence, no comparisons possible).
                block_offset = char_cursor
                block_lines = [line]
                flush_block()
                block_lines = []
            block_offset = char_cursor + line_len_with_nl
            char_cursor += line_len_with_nl
            continue
        # Prose line — accumulate into current block.
        if not block_lines:
            block_offset = char_cursor
        block_lines.append(line)
        char_cursor += line_len_with_nl

    flush_block()

    findings.sort(key=lambda f: (f.offset, f.kind))
    return findings


def _classify(
    a: str,
    b: str,
    *,
    near_max_edits: int,
    near_min_tokens: int,
) -> str | None:
    if a == b:
        return "exact_repeat"
    if a.lower() == b.lower():
        return "case_repeat"
    ta = _tokenize(a)
    tb = _tokenize(b)
    if len(ta) < near_min_tokens or len(tb) < near_min_tokens:
        return None
    dist = _edit_distance_tokens(ta, tb, near_max_edits)
    if 0 < dist <= near_max_edits:
        return "near_repeat"
    return None


def _detail_for(kind: str, a: str, b: str) -> str:
    if kind == "exact_repeat":
        return "two adjacent sentences are byte-identical"
    if kind == "case_repeat":
        return "two adjacent sentences differ only in letter case"
    # near_repeat
    ta = _tokenize(a)
    tb = _tokenize(b)
    dist = _edit_distance_tokens(ta, tb, max(len(ta), len(tb)))
    return (
        f"two adjacent sentences differ by {dist} token edit(s); "
        f"len_a={len(ta)} tokens, len_b={len(tb)} tokens"
    )


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no consecutive-identical-sentence stutter detected.\n"
    out = [f"FOUND {len(findings)} stutter finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] offset={f.offset} :: {f.detail}"
        )
        out.append(f"    a={f.sentence_a!r}")
        out.append(f"    b={f.sentence_b!r}")
    out.append("")
    return "\n".join(out)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_stutter",
    "format_report",
]

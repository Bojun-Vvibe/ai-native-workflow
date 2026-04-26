"""Pure-stdlib detector for inconsistent spacing after sentence-ending
punctuation in an LLM Markdown / prose output blob.

The bug class:

  Modern publishing convention is ONE space after a sentence-ending
  punctuation mark (`.`, `!`, `?`). The 19th-century / typewriter
  convention was TWO spaces. LLMs trained on a mix of corpora emit
  both — sometimes within the same paragraph — because their
  training data is a mix of typewriter-era OCR, modern publishing,
  and code comments where double-space is sometimes a deliberate
  alignment trick.

  Mixed spacing is invisible in HTML render (every browser collapses
  runs of spaces) but is real in:

    - the Markdown source bytes (token cost, diff churn)
    - any plain-text consumer (terminals, plain-text email,
      `git log`, log shippers) that does NOT collapse runs
    - any regex / parser that tokenizes on whitespace and treats
      "1 space" vs "2 spaces" as different (some sentence
      tokenizers do)

  This template flags MIXING within one document, not the choice
  itself. A doc that is 100% one-space passes; a doc that is 100%
  two-space passes; a doc that mixes the two (or stacks 3+ spaces
  anywhere) fires.

Findings:

  - `mixed_sentence_spacing` — the document contains MORE THAN ONE
    sentence-spacing convention (one-space sentences AND two-space
    sentences both present). Reported once, scope=blob, with the
    inventory (`one_space=N two_space=N`).

  - `excess_space_after_period` — a run of 3+ spaces after a
    sentence-ending punctuation. Reported per occurrence with the
    1-based line number, column of the punctuation, and run length.
    A 3+ run is never legitimate sentence spacing; it's either an
    OCR bleed-through or a model that lost track of its own style
    mid-paragraph.

  - `two_space_in_one_space_blob` — a two-space gap in a blob whose
    majority sentence convention is one-space. Reported per
    occurrence so the fix is line-precise.

  - `one_space_in_two_space_blob` — a one-space gap in a blob whose
    majority sentence convention is two-space. Reported per
    occurrence. Symmetric to the above.

  - `tab_after_period` — a TAB character (rather than a space)
    after sentence-ending punctuation. Always wrong in prose;
    reported per occurrence regardless of majority. A model
    emitting a tab mid-prose is leaking a Makefile / TSV artifact.

A "sentence-ending punctuation" is `.` / `!` / `?` followed by at
least one whitespace character followed by a capital letter or an
opening quote/bracket. The capital-letter requirement is the
load-bearing filter that prevents flagging:

  - decimals (`3.14`)
  - filenames / URLs (`config.yaml is loaded`)
  - abbreviations (`e.g. the next item`)
  - file extensions (`.py files`)

A `.` followed by 1+ space followed by a lowercase word is
considered NOT a sentence boundary (almost certainly an
abbreviation or a continuation). False negatives on legitimate
sentences that start with a lowercase brand name (`iPhone`, `iOS`)
are a deliberate trade — false positives on `e.g.` / `i.e.` /
`vs.` would be far noisier.

Pure: input is `str`, no I/O, no third-party deps, no NLP model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    column: int
    detail: str


_KINDS = (
    "mixed_sentence_spacing",
    "excess_space_after_period",
    "two_space_in_one_space_blob",
    "one_space_in_two_space_blob",
    "tab_after_period",
)


# Sentence-boundary candidate:
#   - punctuation: . ! ?
#   - then: one or more spaces OR one or more tabs
#   - then: a capital letter OR an opening quote/bracket
# Captured: (punct)(whitespace_run)(opener)
_BOUNDARY_RE = re.compile(r"([.!?])([ \t]+)([\"'(\[A-Z])")


def _line_col_of(text: str, offset: int) -> Tuple[int, int]:
    """Return (1-based line, 1-based column) of the byte at `offset`."""
    # Count newlines before offset for the line number.
    line = text.count("\n", 0, offset) + 1
    # Find the start of that line.
    line_start = text.rfind("\n", 0, offset) + 1  # -1 + 1 = 0 for line 1
    col = offset - line_start + 1
    return line, col


def detect_double_space_after_period(text: str) -> List[Finding]:
    """Detect inconsistent / excess sentence spacing in `text`."""
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    findings: List[Finding] = []
    if text == "":
        return findings

    one_space_count = 0
    two_space_count = 0
    excess_runs: List[Tuple[int, int]] = []  # (offset_of_punct, run_length)
    tab_runs: List[Tuple[int, int]] = []  # (offset_of_punct, run_length)
    boundary_kinds: List[Tuple[int, str]] = []  # (offset_of_punct, "one"|"two")

    for m in _BOUNDARY_RE.finditer(text):
        punct_offset = m.start(1)
        ws = m.group(2)
        # Ignore boundaries that span a newline (the "spaces" are line wrap).
        # Our regex already restricts to [ \t] so newlines are excluded —
        # but a CR alone is also excluded. Good.
        if "\t" in ws:
            tab_runs.append((punct_offset, len(ws)))
            continue
        # Pure-space run.
        n = len(ws)
        if n == 1:
            one_space_count += 1
            boundary_kinds.append((punct_offset, "one"))
        elif n == 2:
            two_space_count += 1
            boundary_kinds.append((punct_offset, "two"))
        else:
            excess_runs.append((punct_offset, n))

    distinct_majorities = sum(
        1 for c in (one_space_count, two_space_count) if c > 0
    )

    # mixed_sentence_spacing summary (line_number=0, scope=blob)
    if distinct_majorities > 1:
        findings.append(
            Finding(
                kind="mixed_sentence_spacing",
                line_number=0,
                column=0,
                detail=(
                    f"blob mixes sentence-spacing conventions: "
                    f"one_space={one_space_count} two_space={two_space_count}"
                ),
            )
        )

    # Decide majority for the per-occurrence reports.
    # On a tie, prefer one-space (modern convention).
    majority = None
    if distinct_majorities >= 2:
        majority = "one" if one_space_count >= two_space_count else "two"

    # Per-occurrence: minority-spacing reports
    if majority is not None:
        for offset, kind in boundary_kinds:
            if kind == majority:
                continue
            ln, col = _line_col_of(text, offset)
            if majority == "one" and kind == "two":
                findings.append(
                    Finding(
                        kind="two_space_in_one_space_blob",
                        line_number=ln,
                        column=col,
                        detail="two-space sentence gap in a one-space-majority blob",
                    )
                )
            elif majority == "two" and kind == "one":
                findings.append(
                    Finding(
                        kind="one_space_in_two_space_blob",
                        line_number=ln,
                        column=col,
                        detail="one-space sentence gap in a two-space-majority blob",
                    )
                )

    # excess_space_after_period: ALWAYS reported (3+ is never sentence spacing)
    for offset, n in excess_runs:
        ln, col = _line_col_of(text, offset)
        findings.append(
            Finding(
                kind="excess_space_after_period",
                line_number=ln,
                column=col,
                detail=f"run of {n} spaces after sentence-ending punctuation",
            )
        )

    # tab_after_period: ALWAYS reported
    for offset, n in tab_runs:
        ln, col = _line_col_of(text, offset)
        findings.append(
            Finding(
                kind="tab_after_period",
                line_number=ln,
                column=col,
                detail=f"tab character(s) after sentence-ending punctuation (run length {n})",
            )
        )

    findings.sort(
        key=lambda f: (
            f.line_number,
            f.column,
            _KINDS.index(f.kind) if f.kind in _KINDS else 99,
        )
    )
    return findings


def format_report(findings: List[Finding]) -> str:
    if not findings:
        return "OK: sentence spacing is consistent.\n"
    lines = [f"FOUND {len(findings)} sentence-spacing finding(s):"]
    for f in findings:
        if f.line_number == 0:
            loc = "scope=blob"
        else:
            loc = f"line={f.line_number} col={f.column}"
        lines.append(f"  [{f.kind}] {loc} :: {f.detail}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_double_space_after_period",
    "format_report",
]

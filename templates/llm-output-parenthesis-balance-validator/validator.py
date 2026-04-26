"""Pure-stdlib validator for parenthesis `(` / `)` balance and nesting in
an LLM prose / Markdown output blob.

Square brackets `[ ]` and curly braces `{ }` are deliberately OUT of
scope here — they have legitimate Markdown semantics (link reference
syntax, footnote syntax, template placeholders) and are covered by
sibling templates (`llm-output-citation-bracket-balance-validator`,
`llm-output-quotation-mark-balance-validator`). This validator owns
ONE axis: the round paren `(` / `)` that LLMs use for parenthetical
asides and that they routinely under-close or over-close when
streaming long sentences with mid-clause clarifications.

Four finding kinds:

  - `unmatched_open`  — a `(` with no matching `)` before EOF.
    One finding PER unmatched open, anchored at its 1-based line
    number and 1-based column.
  - `unmatched_close` — a `)` with no preceding unmatched `(`.
    One finding per occurrence, anchored at line/column of the `)`.
  - `excessive_nesting` — at any point the live open-paren depth
    exceeds `max_depth` (default 3). Reported once per RUN that
    crossed the threshold (not once per char that stayed above it),
    anchored at the `(` that pushed depth above the threshold.
  - `inside_code_paren_skipped` (informational, count-only summary)
    — number of paren chars that were ignored because they sit
    inside a fenced code block (` ``` `) or an inline code span
    (`` ` ``). Reported once at line 1 with the skipped count, so
    the operator can tell whether a "balanced" report is balanced
    in the prose layer or just because most of the parens were in
    code. Suppress by passing `report_skipped=False`.

Code-aware scope: the validator tracks fenced code blocks (ATX-style
`````` opening/closing on their own line, optionally with an info
string) and inline backtick spans. Parens inside either are NOT
counted toward balance — `print("hello (world)")` inside a Python
fence has no business raising `unmatched_close`.

Pure: input is `str`, no I/O, no third-party deps, no Markdown
parser. The fence/inline-code detection is intentionally minimal
(matches what every CommonMark renderer agrees on) and is
documented in `Limitations` below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    column: int
    detail: str


_KINDS = (
    "inside_code_paren_skipped",
    "unmatched_open",
    "unmatched_close",
    "excessive_nesting",
)


def validate_parenthesis_balance(
    text: str,
    *,
    max_depth: int = 3,
    report_skipped: bool = True,
) -> List[Finding]:
    """Validate `(` / `)` balance and nesting depth in `text`.

    Args:
      text: the LLM output blob to scan.
      max_depth: maximum tolerated live open-paren depth before
        `excessive_nesting` fires. Default 3 (one parenthetical
        inside another inside another is the practical readability
        ceiling for prose). Set to 1 to forbid any nested parens
        (strict business-writing style).
      report_skipped: if True (default), emit a single
        `inside_code_paren_skipped` summary finding when any paren
        char was ignored inside code. Set False for a strictly
        finding-only report.

    Returns:
      Sorted list of Finding records — stable sort by
      (line_number, column, kind).
    """
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    if not isinstance(max_depth, int) or isinstance(max_depth, bool):
        raise ValidationError(
            f"max_depth must be int, got {type(max_depth).__name__}"
        )
    if max_depth < 1:
        raise ValidationError(f"max_depth must be >= 1, got {max_depth}")

    findings: List[Finding] = []
    if text == "":
        return findings

    lines = text.split("\n")
    in_fence = False  # inside a ```...``` fenced code block
    open_stack: List[tuple] = []  # entries: (line, col) of unmatched `(`
    skipped_in_code = 0
    above_threshold = False  # currently inside an excessive-nesting run

    for li, raw_line in enumerate(lines, start=1):
        # Fenced-code toggle: a line whose first non-space chars are
        # 3+ backticks. (CommonMark also accepts ~~~ fences; we cover
        # backtick fences only — see Limitations.)
        stripped = raw_line.lstrip(" ")
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        if in_fence:
            # All parens inside a fenced block are skipped from balance.
            for ch in raw_line:
                if ch == "(" or ch == ")":
                    skipped_in_code += 1
            continue

        # Not in a fence: walk the line, tracking inline backtick spans.
        in_inline_code = False
        col = 0
        for ch in raw_line:
            col += 1
            if ch == "`":
                in_inline_code = not in_inline_code
                continue
            if in_inline_code:
                if ch == "(" or ch == ")":
                    skipped_in_code += 1
                continue
            if ch == "(":
                open_stack.append((li, col))
                # excessive_nesting: fire on the OPEN that crosses threshold,
                # but only once per contiguous run above the threshold.
                if len(open_stack) > max_depth and not above_threshold:
                    above_threshold = True
                    findings.append(
                        Finding(
                            kind="excessive_nesting",
                            line_number=li,
                            column=col,
                            detail=(
                                f"open-paren depth reached {len(open_stack)} "
                                f"(max allowed: {max_depth})"
                            ),
                        )
                    )
            elif ch == ")":
                if open_stack:
                    open_stack.pop()
                    if len(open_stack) <= max_depth:
                        above_threshold = False
                else:
                    findings.append(
                        Finding(
                            kind="unmatched_close",
                            line_number=li,
                            column=col,
                            detail="')' has no matching preceding '('",
                        )
                    )

    # Anything left on the stack is an unmatched open.
    for (li, col) in open_stack:
        findings.append(
            Finding(
                kind="unmatched_open",
                line_number=li,
                column=col,
                detail="'(' has no matching ')' before EOF",
            )
        )

    if report_skipped and skipped_in_code > 0:
        findings.append(
            Finding(
                kind="inside_code_paren_skipped",
                line_number=1,
                column=1,
                detail=(
                    f"{skipped_in_code} paren char(s) ignored inside code "
                    f"(fenced block or inline span)"
                ),
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
        return "OK: parentheses balanced.\n"
    lines = [f"FOUND {len(findings)} paren finding(s):"]
    for f in findings:
        lines.append(
            f"  [{f.kind}] line={f.line_number} col={f.column} :: {f.detail}"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "Finding",
    "ValidationError",
    "validate_parenthesis_balance",
    "format_report",
]

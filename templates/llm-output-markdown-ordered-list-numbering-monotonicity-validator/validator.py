"""Pure stdlib validator for ordered-list numbering monotonicity in
LLM-generated markdown.

Detects four kinds of finding on every contiguous ordered-list block
(per indent level, fence-aware):

  - non_monotonic   :: numbers do not strictly increase by +1
                       within a block at a given indent level
                       (e.g. `1.` `2.` `4.` — skipped 3,
                        or `1.` `3.` `2.` — went backwards).
  - bad_start       :: the block does not start at 1 (and was not
                       declared with `start_at` for that nesting
                       level — by default every fresh ordered list
                       at any indent must open at 1).
  - mixed_marker    :: a single block mixes `.` and `)` markers
                       (`1.` then `2)`); markdown renderers handle
                       this inconsistently and the LLM almost
                       certainly meant one or the other.
  - duplicate_index :: the same index appears twice in one block
                       (`1.` `2.` `2.` `3.`); a special-case of
                       non_monotonic worth flagging on its own
                       because it is a copy-paste signature, not a
                       counting-from-the-wrong-place bug.

A "block" terminates on:

  - a blank line (paragraph break)
  - a non-list line at the same-or-shallower indent
  - end of input
  - a fenced-code-block opener (` ``` ` / `~~~`)

Lines INSIDE a fenced code block are skipped entirely so a code
sample like

    ```python
    1. one
    2. two
    4. four   # <- intentional in the example
    ```

does not flag.

Nested ordered lists are tracked independently per indent column, so

    1. outer
       1. inner
       2. inner
    2. outer
       1. inner

is clean (two outer items, two inner under outer-1, one inner under
outer-2 — each inner block restarts at 1 because the parent item
boundary closes the previous inner block).

Public API:

    validate_ordered_list_numbering(text: str) -> list[Finding]
    format_report(findings: list[Finding]) -> str

Pure function: no I/O, no markdown library, no regex backtracking
hazards. The only state is a tiny stack of (indent, expected_next,
marker, items_seen) frames.
"""

from __future__ import annotations

from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised on input that is not a `str`."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line_no: int  # 1-based
    indent: int
    detail: str
    sample: str  # the offending line, stripped of trailing newline


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _leading_spaces(line: str) -> int:
    """Count leading spaces. A tab counts as 4 spaces (CommonMark default)."""
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4 - (n % 4)
        else:
            break
    return n


def _parse_ordered_marker(line: str) -> tuple[int, str, str] | None:
    """Return (number, marker_char, rest) for an ordered-list line, else None.

    Recognized form: optional indent, then digits, then `.` or `)`, then a
    single space, then the item body. Markers must have a body or EOL after
    the space (a bare `1.` with no space is intentionally NOT a list item;
    that matches CommonMark and prevents `1.5` from being mis-parsed).
    """
    stripped = line.lstrip(" \t")
    i = 0
    while i < len(stripped) and stripped[i].isdigit():
        i += 1
    if i == 0 or i > 9:
        # No digits, or absurdly long run that no human writes.
        return None
    if i >= len(stripped):
        return None
    marker = stripped[i]
    if marker not in (".", ")"):
        return None
    rest = stripped[i + 1 :]
    # CommonMark: marker must be followed by a space (or end of line).
    if rest and not rest.startswith(" "):
        return None
    try:
        number = int(stripped[:i])
    except ValueError:
        return None
    return number, marker, rest.lstrip(" ")


def _is_blank(line: str) -> bool:
    return line.strip() == ""


def _is_fence_line(line: str) -> bool:
    s = line.lstrip(" \t")
    return s.startswith("```") or s.startswith("~~~")


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    indent: int
    expected_next: int
    marker: str
    seen_indices: set
    started_at_line: int


def validate_ordered_list_numbering(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")

    findings: list[Finding] = []
    lines = text.splitlines()

    # Stack of active ordered-list blocks, deepest last.
    stack: list[_Block] = []
    in_fence = False
    fence_marker = ""

    def close_blocks_at_or_below(indent: int) -> None:
        while stack and stack[-1].indent >= indent:
            stack.pop()

    def close_all() -> None:
        stack.clear()

    for idx, raw in enumerate(lines, start=1):
        # Fence handling — fence lines themselves never create or close list
        # blocks except by ending the surrounding paragraph (blank-line
        # semantics): we treat a fence line as a hard block break.
        if _is_fence_line(raw):
            if not in_fence:
                in_fence = True
                fence_marker = raw.lstrip(" \t")[:3]
                close_all()
            else:
                # Closing fence (any matching marker prefix is good enough).
                if raw.lstrip(" \t").startswith(fence_marker):
                    in_fence = False
                    fence_marker = ""
            continue

        if in_fence:
            continue

        if _is_blank(raw):
            close_all()
            continue

        parsed = _parse_ordered_marker(raw)
        indent = _leading_spaces(raw)

        if parsed is None:
            # A non-list line: close any block at deeper-or-equal indent
            # (a paragraph at the same indent ends the list; an indented
            # continuation line under a list item does NOT — it would have
            # indent > the list's marker indent + 2).
            close_blocks_at_or_below(indent)
            continue

        number, marker, _body = parsed

        # Close deeper blocks (we have stepped back out a level).
        while stack and stack[-1].indent > indent:
            stack.pop()

        if not stack or stack[-1].indent < indent:
            # New (possibly nested) block.
            block = _Block(
                indent=indent,
                expected_next=2,  # next item should be 2 if this opened at 1
                marker=marker,
                seen_indices={number},
                started_at_line=idx,
            )
            if number != 1:
                findings.append(
                    Finding(
                        kind="bad_start",
                        line_no=idx,
                        indent=indent,
                        detail=(
                            f"ordered list opens at {number}{marker} "
                            "but should open at 1"
                        ),
                        sample=raw.rstrip("\n"),
                    )
                )
                # Resync expected_next so we report each subsequent
                # off-by-one once, not on every line of the block.
                block.expected_next = number + 1
            stack.append(block)
            continue

        # Continuing the current block at this indent.
        block = stack[-1]
        if marker != block.marker:
            findings.append(
                Finding(
                    kind="mixed_marker",
                    line_no=idx,
                    indent=indent,
                    detail=(
                        f"item uses {marker!r} but block opened with "
                        f"{block.marker!r} at line {block.started_at_line}"
                    ),
                    sample=raw.rstrip("\n"),
                )
            )
        if number in block.seen_indices:
            findings.append(
                Finding(
                    kind="duplicate_index",
                    line_no=idx,
                    indent=indent,
                    detail=f"index {number} already used in this block",
                    sample=raw.rstrip("\n"),
                )
            )
        elif number != block.expected_next:
            findings.append(
                Finding(
                    kind="non_monotonic",
                    line_no=idx,
                    indent=indent,
                    detail=(
                        f"expected {block.expected_next}{block.marker} "
                        f"got {number}{marker}"
                    ),
                    sample=raw.rstrip("\n"),
                )
            )
        block.seen_indices.add(number)
        block.expected_next = number + 1

    return findings


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: ordered-list numbering is monotonic.\n"
    findings = sorted(findings, key=lambda f: (f.line_no, f.kind, f.indent))
    out = [f"FOUND {len(findings)} numbering finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] line={f.line_no} indent={f.indent} :: {f.detail}"
        )
        out.append(f"    | {f.sample}")
    return "\n".join(out) + "\n"

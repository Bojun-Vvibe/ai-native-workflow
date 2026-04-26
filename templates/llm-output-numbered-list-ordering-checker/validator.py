r"""Numbered-list ordering checker for LLM Markdown output.

Pure stdlib, no I/O. Scans an LLM output blob and reports four
finding kinds for ordered (numbered) list items:

  - non_monotonic     a list item's number is <= the previous item's
                      number in the same list (1, 2, 2, 3 OR 1, 3, 2)
  - skipped_number    a list item's number jumps by more than 1 in
                      a list whose first item starts at 1
                      (1, 2, 4, 5 — the "4" is reported)
  - bad_start         the first item of a list does not start at 1
                      (and not at 0, which is rare-but-deliberate
                      for tutorial counting). Reported once at the
                      first item's line.
  - mixed_separator   list uses both `1.` and `1)` styles; the
                      separator changes mid-list. Markdown renderers
                      treat the change as a new list, silently
                      restarting numbering in some viewers.

A "list" is a contiguous run of lines whose stripped form matches
the ordered-list item pattern `^(\d+)([.)]) +\S`. The list ends
at the first line that does not match (blank line, prose line,
heading, etc.). Indented sub-lists are tracked independently per
indent level; a top-level list and its 2-space-indented child
list are scored separately.

Lines inside a fenced code block (delimited by ``` or ~~~) are
NOT scanned — code samples often have intentional `1.` `3.`
sequences (e.g. quoting bug repro steps).

Public API:

    detect_ordering_issues(text: str) -> list[Finding]
    format_report(findings: list[Finding]) -> str

Findings are sorted by (line_number, kind).

Why this exists separately from a Markdown linter: most linters
either (a) silently auto-renumber (`prettier --write`) so the
issue disappears in the editor but the original blob still ships
to `gh pr create`, or (b) lint only `1.` style and miss `1)`
entirely. The interesting failures are model artifacts where the
list says `1. 2. 4. 5.` because the model "thought" it had
written a third item but the token slipped — a renderer dutifully
shows "1, 2, 3, 4" and the missing item is now invisible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised on bad input."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    column: int
    raw: str
    detail: str


# Ordered-list item: optional indent, digits, "." or ")", one+ space, content.
_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<num>\d+)(?P<sep>[.)]) +\S")
_FENCE_CHARS = ("```", "~~~")


@dataclass
class _ListState:
    indent: str          # indent prefix that defines this list level
    sep: str             # "." or ")" — the separator first seen
    first_num: int       # first item's number (used for bad_start)
    first_line: int      # 1-based line of first item
    last_num: int        # most recent number in this list
    last_line: int       # 1-based line of most recent item
    bad_start_reported: bool = False


def detect_ordering_issues(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")

    findings: list[Finding] = []
    in_fence = False
    fence_char: str | None = None

    # Stack of currently-open lists, keyed by indent depth (string).
    # Lists at deeper indent are children of shallower ones; popping
    # happens when a non-item line closes the run, OR when a sibling
    # list at the same indent restarts.
    open_lists: dict[str, _ListState] = {}

    lines = text.split("\n")
    if text.endswith("\n") and lines and lines[-1] == "":
        lines = lines[:-1]

    def _close_all_at_or_deeper(indent_threshold: int) -> None:
        # Close any list whose indent length is >= the threshold.
        to_drop = [
            k for k in open_lists
            if len(k.expandtabs(4)) >= indent_threshold
        ]
        for k in to_drop:
            del open_lists[k]

    for idx, raw in enumerate(lines, start=1):
        stripped = raw.lstrip(" \t")

        # Fence handling.
        is_fence_line = False
        for fc in _FENCE_CHARS:
            if stripped.startswith(fc):
                is_fence_line = True
                if not in_fence:
                    in_fence = True
                    fence_char = fc
                elif fence_char == fc:
                    in_fence = False
                    fence_char = None
                break
        if is_fence_line:
            # A fence boundary closes any open lists at any indent.
            open_lists.clear()
            continue
        if in_fence:
            continue

        m = _ITEM_RE.match(raw)
        if not m:
            # Non-item line. A blank line closes all open lists; a
            # non-blank prose line closes lists at indent >= its own
            # leading indent (looser: just close everything for
            # determinism — Markdown does the same).
            if raw.strip() == "":
                open_lists.clear()
            else:
                # Treat any non-item line as a hard close so a prose
                # paragraph between two `1.` items is two lists, not
                # one — which matches every real renderer.
                open_lists.clear()
            continue

        indent = m.group("indent")
        num = int(m.group("num"))
        sep = m.group("sep")
        item_col = len(indent) + 1  # 1-based column of the digit

        # Close any deeper lists (we de-indented).
        indent_len = len(indent.expandtabs(4))
        to_drop = [
            k for k in open_lists
            if len(k.expandtabs(4)) > indent_len
        ]
        for k in to_drop:
            del open_lists[k]

        st = open_lists.get(indent)
        if st is None:
            # New list at this indent.
            st = _ListState(
                indent=indent,
                sep=sep,
                first_num=num,
                first_line=idx,
                last_num=num,
                last_line=idx,
            )
            open_lists[indent] = st
            if num != 1 and num != 0 and not st.bad_start_reported:
                findings.append(Finding(
                    kind="bad_start",
                    line_number=idx,
                    column=item_col,
                    raw=raw,
                    detail=(
                        f"first item of list starts at {num}; "
                        "expected 1 (or 0 for zero-indexed lists)"
                    ),
                ))
                st.bad_start_reported = True
        else:
            # Continuation of existing list.
            if sep != st.sep:
                findings.append(Finding(
                    kind="mixed_separator",
                    line_number=idx,
                    column=item_col + len(str(num)),
                    raw=raw,
                    detail=(
                        f"separator '{sep}' differs from list's "
                        f"first separator '{st.sep}' (line "
                        f"{st.first_line})"
                    ),
                ))

            if num <= st.last_num:
                findings.append(Finding(
                    kind="non_monotonic",
                    line_number=idx,
                    column=item_col,
                    raw=raw,
                    detail=(
                        f"item number {num} is <= previous "
                        f"item number {st.last_num} "
                        f"(line {st.last_line})"
                    ),
                ))
            elif st.first_num == 1 and num != st.last_num + 1:
                findings.append(Finding(
                    kind="skipped_number",
                    line_number=idx,
                    column=item_col,
                    raw=raw,
                    detail=(
                        f"item number {num} skips from previous "
                        f"item number {st.last_num} "
                        f"(line {st.last_line}); expected "
                        f"{st.last_num + 1}"
                    ),
                ))

            st.last_num = num
            st.last_line = idx

    findings.sort(key=lambda f: (f.line_number, f.kind))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: numbered lists are well-ordered.\n"
    out = [f"FOUND {len(findings)} ordering finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] line={f.line_number} col={f.column} "
            f":: {f.detail}"
        )
        out.append(f"    line={f.raw!r}")
    out.append("")
    return "\n".join(out)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_ordering_issues",
    "format_report",
]

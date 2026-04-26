"""Pure-stdlib detector for inconsistent unordered-list bullet markers.

Markdown unordered lists accept `-`, `*`, and `+` interchangeably, but mixing
markers inside a single document (or worse, inside a single list) is a common
LLM bug class: the model copies a bullet style from training data partway
through a list and silently switches. The rendered HTML is fine, but the raw
markdown stops being grep-able and any downstream linter that pins a single
marker (prettier, markdownlint MD004) will reject it.

This module is a *consistency* gate, not a style enforcer: if the document
uses only one marker, no findings are emitted regardless of which one.

Three finding kinds:

- ``mixed_marker_in_list`` — within a single contiguous list block, more than
  one marker character appears. Reported once per minority-marker line.
- ``mixed_marker_in_document`` — across the whole document, more than one
  marker character appears across separate list blocks. Reported once per
  minority-marker line.
- ``inconsistent_indent_marker`` — a nested bullet uses a different marker
  than its parent at the same depth elsewhere in the document. Reported
  once per offending line.

A "list block" is a maximal run of lines whose stripped form starts with one
of ``- ``, ``* ``, ``+ `` (with optional leading indentation), uninterrupted
by a blank line or a non-bullet line. Indented continuation lines under a
bullet do not break the block.

Pure function: no I/O, no markdown parser dependency, no network. Findings
are sorted by ``(line, column, kind)`` for deterministic CI diffing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


class ValidationError(ValueError):
    """Raised when ``text`` is not a ``str``."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int  # 1-indexed
    column: int  # 1-indexed, position of the bullet marker character
    raw: str  # the marker character itself
    detail: str


# A bullet line: optional indent, then -/*/+, then a single space, then content.
# Fenced code (```), thematic breaks (---, ***), and list markers in inline
# code are intentionally ignored by the surrounding state machine, not the regex.
_BULLET_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+])(?P<space> +)(?P<rest>.*)$")
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
_THEMATIC_RE = re.compile(r"^[ \t]*([-*_])\s*\1\s*\1[\s\1]*$")


def validate_bullet_markers(text: str) -> List[Finding]:
    """Return findings for bullet-marker inconsistency in ``text``.

    The detector classifies each bullet line by ``(indent_width, marker)`` and
    emits findings for minority markers per list block, per document, and per
    indent depth.
    """

    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")

    lines = text.splitlines()
    in_fence = False

    # Per-line bullet records: (line_no, col, indent_width, marker)
    bullets: list[tuple[int, int, int, str]] = []
    # List-block boundaries: list of lists of bullet-record indices
    blocks: list[list[int]] = []
    current_block: list[int] = []

    def flush_block() -> None:
        nonlocal current_block
        if current_block:
            blocks.append(current_block)
            current_block = []

    for idx, raw_line in enumerate(lines, start=1):
        if _FENCE_RE.match(raw_line):
            in_fence = not in_fence
            flush_block()
            continue
        if in_fence:
            continue
        if not raw_line.strip():
            flush_block()
            continue
        if _THEMATIC_RE.match(raw_line):
            flush_block()
            continue

        m = _BULLET_RE.match(raw_line)
        if m:
            indent = m.group("indent").expandtabs(4)
            indent_width = len(indent)
            marker = m.group("marker")
            col = len(m.group("indent")) + 1
            rec_idx = len(bullets)
            bullets.append((idx, col, indent_width, marker))
            current_block.append(rec_idx)
        else:
            # Continuation line under a bullet keeps the block alive only if
            # it is indented past the most recent bullet's marker; otherwise
            # the block ends.
            if current_block:
                last = bullets[current_block[-1]]
                last_marker_col = last[2]
                stripped_lead = len(raw_line) - len(raw_line.lstrip(" \t"))
                if stripped_lead <= last_marker_col:
                    flush_block()
            else:
                flush_block()

    flush_block()

    findings: list[Finding] = []

    # 1. Per-block mixed marker.
    for block in blocks:
        markers_in_block = [bullets[i][3] for i in block]
        unique = set(markers_in_block)
        if len(unique) > 1:
            counts = {ch: markers_in_block.count(ch) for ch in unique}
            majority = max(counts.items(), key=lambda kv: (kv[1], -ord(kv[0])))[0]
            for i in block:
                line_no, col, _indent, marker = bullets[i]
                if marker != majority:
                    findings.append(
                        Finding(
                            kind="mixed_marker_in_list",
                            line=line_no,
                            column=col,
                            raw=marker,
                            detail=f"block markers={dict(sorted(counts.items()))}; majority={majority!r}",
                        )
                    )

    # 2. Document-wide mixed marker (only across distinct blocks).
    if len(blocks) > 1:
        per_block_marker = []
        for block in blocks:
            markers_in_block = [bullets[i][3] for i in block]
            counts = {ch: markers_in_block.count(ch) for ch in set(markers_in_block)}
            dominant = max(counts.items(), key=lambda kv: (kv[1], -ord(kv[0])))[0]
            per_block_marker.append(dominant)
        unique_doc = set(per_block_marker)
        if len(unique_doc) > 1:
            doc_counts = {ch: per_block_marker.count(ch) for ch in unique_doc}
            doc_majority = max(doc_counts.items(), key=lambda kv: (kv[1], -ord(kv[0])))[0]
            for block, dominant in zip(blocks, per_block_marker):
                if dominant != doc_majority:
                    # Report only the first bullet of the offending block.
                    first = bullets[block[0]]
                    findings.append(
                        Finding(
                            kind="mixed_marker_in_document",
                            line=first[0],
                            column=first[1],
                            raw=dominant,
                            detail=f"document blocks by dominant marker={dict(sorted(doc_counts.items()))}; majority={doc_majority!r}",
                        )
                    )

    # 3. Inconsistent marker at the same indent depth across the document.
    by_depth: dict[int, list[tuple[int, int, str]]] = {}
    for line_no, col, indent_width, marker in bullets:
        by_depth.setdefault(indent_width, []).append((line_no, col, marker))
    for depth, recs in by_depth.items():
        markers_at_depth = [m for _l, _c, m in recs]
        unique_d = set(markers_at_depth)
        if len(unique_d) > 1:
            counts_d = {ch: markers_at_depth.count(ch) for ch in unique_d}
            majority_d = max(counts_d.items(), key=lambda kv: (kv[1], -ord(kv[0])))[0]
            for line_no, col, marker in recs:
                if marker != majority_d:
                    findings.append(
                        Finding(
                            kind="inconsistent_indent_marker",
                            line=line_no,
                            column=col,
                            raw=marker,
                            detail=f"indent={depth}; markers={dict(sorted(counts_d.items()))}; majority={majority_d!r}",
                        )
                    )

    findings.sort(key=lambda f: (f.line, f.column, f.kind))
    return findings


def format_report(findings: List[Finding]) -> str:
    """Render a deterministic plain-text report. Empty findings → OK line."""

    if not findings:
        return "OK: bullet markers are consistent."
    out = [f"FOUND {len(findings)} bullet-marker finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] line={f.line} col={f.column} raw={f.raw!r} :: {f.detail}"
        )
    return "\n".join(out)

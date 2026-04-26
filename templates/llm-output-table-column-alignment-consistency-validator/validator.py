"""
llm-output-table-column-alignment-consistency-validator

Walks GFM markdown tables in an LLM output and audits the *alignment
delimiter* row (the `|---|:---:|---:|` line) against four structural
rules. The cardinality of the table is taken as a given — pair this
with `llm-output-table-column-cardinality-validator` if you need that
gate too.

Findings:

- `invalid_delimiter_cell` — a delimiter cell does not match the GFM
  shape `:?-{1,}:?` (after stripping whitespace). Renderers fall back
  to "treat as paragraph" and the table disappears.
- `mixed_alignment_in_column` — same column index uses two different
  alignments across the document (e.g. left in table 1, right in
  table 2). The model has drifted; downstream eyeballers will see
  numbers right-justified in one place and left-justified in
  another.
- `numeric_column_not_right_aligned` — every body cell in a column
  parses as a number (int / float / percent / currency-prefixed)
  but the alignment is `left` or `none`. This is the single most
  common readability regression in LLM-generated reports.
- `header_alignment_textual_mismatch` — the header word ends in
  ` (%)`, ` (USD)`, ` count`, ` total`, ` #`, ` qty` (case
  insensitive) — i.e. it is *self-declaring numeric* — but the
  column alignment is not `right`.

Pure stdlib. Deterministic ordering: `(table_index, column_index,
kind)`.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Iterable


_DELIM_CELL = re.compile(r"^\s*:?-{1,}:?\s*$")
_NUMERIC_HEADER_SUFFIX = re.compile(
    r"(\(\s*%\s*\)|\(\s*usd\s*\)|\bcount\b|\btotal\b|#|\bqty\b)\s*$",
    re.IGNORECASE,
)
_NUMERIC_BODY = re.compile(
    r"^\s*[\$€£]?-?\d{1,3}(,\d{3})*(\.\d+)?\s*%?\s*$"
)


@dataclass(frozen=True)
class Finding:
    table_index: int
    column_index: int
    kind: str
    detail: str


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _alignment_of(cell: str) -> str:
    c = cell.strip()
    left = c.startswith(":")
    right = c.endswith(":")
    if left and right:
        return "center"
    if right:
        return "right"
    if left:
        return "left"
    return "none"


def _iter_tables(text: str):
    """Yield (table_index, header_cells, delim_cells, body_rows_cells)."""
    lines = text.splitlines()
    i = 0
    t_idx = 0
    while i < len(lines) - 1:
        line = lines[i]
        nxt = lines[i + 1]
        nxt_cells = _split_row(nxt) if "|" in nxt else []
        looks_delim = (
            "|" in line and nxt_cells
            and sum(1 for c in nxt_cells if _DELIM_CELL.match(c))
            >= max(1, (len(nxt_cells) + 1) // 2)
        )
        if looks_delim:
            header = _split_row(line)
            delim = _split_row(nxt)
            body: list[list[str]] = []
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                body.append(_split_row(lines[j]))
                j += 1
            yield t_idx, header, delim, body
            t_idx += 1
            i = j
            continue
        i += 1


def validate(text: str) -> list[Finding]:
    findings: list[Finding] = []
    column_alignments: dict[int, set[str]] = {}

    for t_idx, header, delim, body in _iter_tables(text):
        for col_idx, cell in enumerate(delim):
            if not _DELIM_CELL.match(cell):
                findings.append(Finding(
                    table_index=t_idx,
                    column_index=col_idx,
                    kind="invalid_delimiter_cell",
                    detail=f"cell={cell!r}",
                ))

        aligns = [_alignment_of(c) if _DELIM_CELL.match(c) else "none"
                  for c in delim]

        for col_idx, a in enumerate(aligns):
            column_alignments.setdefault(col_idx, set()).add(a)

        for col_idx, a in enumerate(aligns):
            if col_idx >= len(header):
                continue
            head = header[col_idx]
            if _NUMERIC_HEADER_SUFFIX.search(head) and a != "right":
                findings.append(Finding(
                    table_index=t_idx,
                    column_index=col_idx,
                    kind="header_alignment_textual_mismatch",
                    detail=f"header={head!r} alignment={a}",
                ))

        for col_idx, a in enumerate(aligns):
            col_cells = [r[col_idx] for r in body
                         if col_idx < len(r) and r[col_idx]]
            if not col_cells:
                continue
            if all(_NUMERIC_BODY.match(c) for c in col_cells) and \
                    a in ("left", "none"):
                findings.append(Finding(
                    table_index=t_idx,
                    column_index=col_idx,
                    kind="numeric_column_not_right_aligned",
                    detail=f"alignment={a} sample={col_cells[0]!r}",
                ))

    for col_idx, aset in column_alignments.items():
        non_none = aset - {"none"}
        if len(non_none) >= 2:
            findings.append(Finding(
                table_index=-1,
                column_index=col_idx,
                kind="mixed_alignment_in_column",
                detail="alignments=" + ",".join(sorted(non_none)),
            ))

    findings.sort(key=lambda f: (f.table_index, f.column_index, f.kind))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validator.py <file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        text = fh.read()
    findings = validate(text)
    print(json.dumps([asdict(f) for f in findings], indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

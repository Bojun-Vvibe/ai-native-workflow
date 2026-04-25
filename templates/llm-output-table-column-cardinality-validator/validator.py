"""
llm-output-table-column-cardinality-validator
=============================================

Pure stdlib validator for GFM-style markdown tables emitted by an LLM.
The model loves to say "here is a 4-column table" and then drop a column
in row 7, or split a cell with an unescaped pipe, or forget the
alignment delimiter row entirely. Downstream renderers (most agent UIs,
Slack, GitHub) silently *rewrite* such tables — duplicating cells,
shifting columns, or rendering as paragraph text — so the operator sees
"a table" and never notices the data drift.

This validator finds every fenced or unfenced markdown table in an
input string and reports, per table:

  - missing_delimiter   : row 1 looks like a header but row 2 is not
                          a `|---|---|` delimiter line. Most renderers
                          will *not* render the block as a table at all.
  - column_count_mismatch :
                          a body row has a different number of cells
                          than the header. Reports `expected` and
                          `actual` and the offending row index.
  - delimiter_count_mismatch :
                          the `---` delimiter row has a different
                          number of cells than the header.
  - unescaped_pipe       :
                          a body row contains a literal `|` *inside*
                          a cell (not a separator) that wasn't escaped
                          as `\\|` — heuristic: a row that contains the
                          target column count + N extra `|`s where the
                          extras land in a single cell. Surfaced because
                          it's by far the most common cause of a
                          "row is one column too long" mismatch.
  - empty_table          :
                          header row exists but no body rows follow.

Hard rule: pure function over a string. No I/O, no clocks. Caller
decides whether to fail CI, repair the table, or quarantine the output.

Why this exists as its own template:

  - "the model emitted bad markdown" is one of the most common silent
    failure modes for any agent that produces structured human-facing
    output. The bug is invisible at the prompt-eval layer (output is
    "a table") and only surfaces when a downstream tool tries to
    parse it as CSV or feed it back into another LLM call.
  - The taxonomy distinction matters: `missing_delimiter` is a
    formatter bug ("model forgot the spec"); `column_count_mismatch`
    is a data bug ("model has a row it doesn't know how to fit");
    `unescaped_pipe` is a tokenizer bug ("model put a `|` in a cell").
    A single "table is broken" error string conflates three different
    fixes in three different layers.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


# A markdown table block: contiguous lines that all start (after optional
# leading whitespace) with `|` and contain at least one more `|`.
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
# A delimiter row: pipes around `:?-+:?` per cell.
_DELIM_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")


@dataclass(frozen=True)
class Finding:
    kind: str
    table_index: int          # 0-based index of the table in the document
    row_index: Optional[int]  # 0-based row within the table, or None for table-wide
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TableReport:
    table_index: int
    start_line: int           # 1-based source line where the table begins
    end_line: int             # 1-based source line where the table ends (inclusive)
    header_columns: int
    body_rows: int
    findings: List[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "table_index": self.table_index,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "header_columns": self.header_columns,
            "body_rows": self.body_rows,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class DocumentReport:
    table_count: int
    findings: List[Finding] = field(default_factory=list)
    tables: List[TableReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        # finding-kind tally for cron diffing
        tally: dict = {}
        for f in self.findings:
            tally[f.kind] = tally.get(f.kind, 0) + 1
        return {
            "ok": self.ok,
            "table_count": self.table_count,
            "finding_kind_totals": dict(sorted(tally.items())),
            "findings": [f.to_dict() for f in sorted(
                self.findings,
                key=lambda x: (x.table_index, x.row_index if x.row_index is not None else -1, x.kind),
            )],
            "tables": [t.to_dict() for t in self.tables],
        }


def _split_row(line: str) -> List[str]:
    """
    Split one markdown table row on unescaped `|`. Returns the cells
    *between* the leading and trailing pipes (those are mandatory in
    GFM). A line without a leading or trailing pipe still works
    (drops nothing).
    """
    # Replace escaped pipes with a sentinel that can't appear in user text.
    SENTINEL = "\x00ESCAPED_PIPE\x00"
    s = line.replace("\\|", SENTINEL)
    s = s.strip()
    # Strip exactly one leading/trailing `|` if present.
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells = s.split("|")
    return [c.replace(SENTINEL, "|").strip() for c in cells]


def _is_delimiter_row(cells: List[str]) -> bool:
    if not cells:
        return False
    return all(_DELIM_CELL_RE.match(c) for c in cells)


def _find_table_blocks(lines: List[str]) -> List[Tuple[int, int]]:
    """
    Return list of (start_idx, end_idx) inclusive, 0-based, for each
    contiguous run of table-shaped lines.
    """
    blocks: List[Tuple[int, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        if _TABLE_LINE_RE.match(lines[i]):
            j = i
            while j < n and _TABLE_LINE_RE.match(lines[j]):
                j += 1
            blocks.append((i, j - 1))
            i = j
        else:
            i += 1
    return blocks


def validate(text: str) -> DocumentReport:
    """
    Validate every markdown-table-like block in *text*. Returns a
    DocumentReport with per-table findings rolled up to the document.
    """
    if not isinstance(text, str):
        raise TypeError("validate() expects str")

    lines = text.splitlines()
    blocks = _find_table_blocks(lines)
    doc = DocumentReport(table_count=len(blocks))

    for table_index, (start, end) in enumerate(blocks):
        block_lines = lines[start : end + 1]
        report = TableReport(
            table_index=table_index,
            start_line=start + 1,
            end_line=end + 1,
            header_columns=0,
            body_rows=0,
        )

        # Row 0 = header.
        header_cells = _split_row(block_lines[0])
        report.header_columns = len(header_cells)

        # Row 1 should be the delimiter.
        has_delim = False
        if len(block_lines) >= 2:
            row1_cells = _split_row(block_lines[1])
            if _is_delimiter_row(row1_cells):
                has_delim = True
                if len(row1_cells) != len(header_cells):
                    report.findings.append(Finding(
                        kind="delimiter_count_mismatch",
                        table_index=table_index,
                        row_index=1,
                        detail=f"delimiter row has {len(row1_cells)} cells; header has {len(header_cells)}",
                    ))

        if not has_delim:
            report.findings.append(Finding(
                kind="missing_delimiter",
                table_index=table_index,
                row_index=None,
                detail="header row not followed by a `|---|---|` delimiter; most renderers will not render this as a table",
            ))

        body_start = 2 if has_delim else 1
        body_lines = block_lines[body_start:]
        report.body_rows = len(body_lines)

        if has_delim and report.body_rows == 0:
            report.findings.append(Finding(
                kind="empty_table",
                table_index=table_index,
                row_index=None,
                detail="header + delimiter present but zero body rows",
            ))

        for k, body_line in enumerate(body_lines):
            row_cells = _split_row(body_line)
            row_index_in_table = body_start + k
            if len(row_cells) != len(header_cells):
                # Heuristic: extra unescaped pipes inside a cell.
                raw = body_line
                # count of `|` excluding escaped, minus the 2 boundary pipes
                stripped = raw.replace("\\|", "")
                pipe_count = stripped.count("|")
                # GFM rows have header_columns + 1 pipes (boundaries +
                # separators). One extra unescaped `|` inside a cell
                # bumps cell count by 1 and pipe_count by 1.
                expected_pipes = len(header_cells) + 1
                if (
                    len(row_cells) > len(header_cells)
                    and pipe_count - expected_pipes == len(row_cells) - len(header_cells)
                ):
                    report.findings.append(Finding(
                        kind="unescaped_pipe",
                        table_index=table_index,
                        row_index=row_index_in_table,
                        detail=(
                            f"row has {len(row_cells)} cells vs header {len(header_cells)}; "
                            f"likely an unescaped `|` inside a cell — escape as `\\|`"
                        ),
                    ))
                else:
                    report.findings.append(Finding(
                        kind="column_count_mismatch",
                        table_index=table_index,
                        row_index=row_index_in_table,
                        detail=(
                            f"row has {len(row_cells)} cells; header expected {len(header_cells)}"
                        ),
                    ))

        doc.tables.append(report)
        doc.findings.extend(report.findings)

    return doc


def _cli() -> int:
    """
    Read markdown from stdin (or argv[1] if given), print JSON report.
    Exit 0 if ok, 1 if findings, 2 on malformed input.
    """
    try:
        if len(sys.argv) > 1 and sys.argv[1] != "-":
            with open(sys.argv[1], "r", encoding="utf-8") as fh:
                text = fh.read()
        else:
            text = sys.stdin.read()
    except OSError as e:
        print(json.dumps({"error": f"io: {e}"}), file=sys.stderr)
        return 2

    report = validate(text)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(_cli())

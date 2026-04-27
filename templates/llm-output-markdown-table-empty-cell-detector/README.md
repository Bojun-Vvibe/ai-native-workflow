# llm-output-markdown-table-empty-cell-detector

## Intent
Detect empty data cells inside GitHub-Flavored Markdown tables. LLMs frequently
emit tables where some cells are blank (e.g. `| foo |  | bar |`) — this is
usually a sign of a missing value, an off-by-one column drift, or sloppy
generation. Empty header cells and empty cells in the alignment/separator row
are also flagged because they almost always indicate a broken table.

This detector does **not** validate column-count consistency (see
`llm-output-markdown-table-column-cardinality-validator` for that). It focuses
purely on the *content* of cells that look syntactically present.

## Inputs
- A single positional argument: path to a UTF-8 markdown file.

## Outputs
- One finding per offending cell, written to stdout, in the form:
  `path:line:col empty cell in {header|separator|body} row col=N`
- Final summary line: `findings: <N>` to stderr.

## Exit codes
- `0` — no findings
- `1` — one or more findings
- `2` — usage error (no path given, file not found, not UTF-8)

## Heuristics
A row is treated as a table row if it starts with optional whitespace then `|`
and contains at least one more `|`. The separator row is the row immediately
following a header row whose cells match `:?-+:?` after trimming.

A cell is "empty" if, after stripping whitespace, it is the empty string. The
leading and trailing pipe-delimited segments outside the outer pipes are
ignored (so `| a | b |` has 2 cells, not 4).

## Run
```
python3 detect.py examples/bad.md   # exit 1, prints findings
python3 detect.py examples/good.md  # exit 0
```

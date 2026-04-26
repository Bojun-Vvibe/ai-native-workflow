# llm-output-table-column-alignment-consistency-validator

Pure stdlib auditor for the *alignment delimiter* row of GFM
markdown tables — the `|---|:---:|---:|` line — emitted by an LLM.

The model loves to emit a numeric column (`Revenue (USD)`,
`Growth (%)`, `Headcount`) with `none` or `left` alignment. In the
GFM renderer that means a column of dollar amounts gets
left-justified next to ragged decimal points and the operator's
eyes glide right past the regression. Worse, the model
intermittently flips alignment between two emissions of "the same"
table — the table looks fine in isolation but yesterday's column
was `right` and today's is `left`.

Four finding classes:

- **`invalid_delimiter_cell`** — a delimiter cell does not match
  the GFM shape `:?-{1,}:?` after stripping whitespace. Most
  renderers fall back to "treat block as paragraph" and the table
  silently disappears.
- **`mixed_alignment_in_column`** — the same column index uses two
  different *explicit* alignments across the document (`none` is
  excluded so a single explicitly-aligned column doesn't trip
  this). Surfaces drift between two tables that ought to look the
  same.
- **`numeric_column_not_right_aligned`** — every non-empty body
  cell in a column parses as a number (int / float / percent /
  `$€£`-prefixed) but the alignment is `left` or `none`. The
  single most common readability regression in LLM-generated
  reports.
- **`header_alignment_textual_mismatch`** — the header text is
  *self-declaring* numeric — ends in ` (%)`, ` (USD)`, ` count`,
  ` total`, ` #`, ` qty` (case-insensitive) — but the column
  alignment is not `right`.

Cardinality is **not** in scope. Pair with
`llm-output-table-column-cardinality-validator` if you also need to
catch dropped/added cells.

## When to use

- Post-decode gate on any LLM output that contains a markdown
  table with a numeric column. Catches the alignment regression
  before the table reaches a renderer or a downstream eyeballer.
- CI assertion on captured prompt-replay fixtures — a regression
  in the prompt that drops the alignment instruction surfaces as
  `numeric_column_not_right_aligned` going from 0 to N
  immediately.
- Diff gate on "the same report, yesterday vs today" — flips
  surface as `mixed_alignment_in_column`.

## When NOT to use

- This is **not** a markdown parser. Five rules over the delimiter
  row only — no inline-link validation, no column-width check, no
  Unicode-numeric handling.
- This is **not** a number parser. The numeric body regex is
  intentionally narrow (US-style `1,234.56`, optional currency
  prefix, optional trailing `%`). EU-style `1.234,56` will read
  as non-numeric and that column will be silently skipped — by
  design, fewer false positives than wrong-locale guesses.
- It does **not** repair tables. Caller decides whether to fail
  CI, drop the output, or feed it to a separate repair pass.

## Design choices worth knowing

- **`mixed_alignment_in_column` ignores `none`.** A document with
  one explicitly-aligned table and one alignment-less table does
  not trip the rule — the alignment-less table is reported
  separately by `numeric_column_not_right_aligned` if it is
  numeric, and otherwise silently. Two-stage taxonomy keeps
  signal-to-noise high.
- **Findings are sorted `(table_index, column_index, kind)`.**
  Two runs over the same input produce byte-identical output, so
  cron-driven alerting can diff yesterday's report against
  today's without false-positive churn. The
  `mixed_alignment_in_column` rows use `table_index = -1` and
  therefore sort to the top of the report.
- **Half-match on the delimiter row** — `_iter_tables` accepts a
  delimiter row where ≥half of cells match the GFM shape, so a
  table with a typo in one cell (`|------|=======|`) is still
  recognized as a table and the bad cell is reported via
  `invalid_delimiter_cell`. Stricter "all cells match" parsing
  would skip the table entirely and the operator would see
  silence.

## Usage

```
python3 validator.py path/to/llm_output.md
```

Exit code `0` if no findings, `1` if any finding, `2` on usage
error. Findings are printed as a JSON array on stdout.

## Worked example

`examples/example.py` embeds three tables — a numeric report with
no alignment, a same-shape table with explicit `center`/`right`
alignments (used to demonstrate the *absence* of a
`mixed_alignment_in_column` false positive), and a third table
with a malformed delimiter cell (`=======`).

Run:

```
$ python3 examples/example.py
```

Output:

```
[
  {
    "table_index": 0,
    "column_index": 1,
    "kind": "header_alignment_textual_mismatch",
    "detail": "header='Revenue (USD)' alignment=none"
  },
  {
    "table_index": 0,
    "column_index": 1,
    "kind": "numeric_column_not_right_aligned",
    "detail": "alignment=none sample='1,200'"
  },
  {
    "table_index": 0,
    "column_index": 2,
    "kind": "header_alignment_textual_mismatch",
    "detail": "header='Growth (%)' alignment=none"
  },
  {
    "table_index": 0,
    "column_index": 2,
    "kind": "numeric_column_not_right_aligned",
    "detail": "alignment=none sample='8.4'"
  },
  {
    "table_index": 2,
    "column_index": 1,
    "kind": "invalid_delimiter_cell",
    "detail": "cell='======='"
  },
  {
    "table_index": 2,
    "column_index": 1,
    "kind": "numeric_column_not_right_aligned",
    "detail": "alignment=none sample='1'"
  }
]
```

Read the report top-to-bottom: table 0 (the AMER/EMEA/APAC report)
has both numeric columns flagged twice — once for the textual
header signal, once for the body-shape signal. Two independent
detectors firing on the same column is intentional; the operator
sees two reasons to fix it. Table 2 (the malformed-delimiter
table) lights up the `invalid_delimiter_cell` rule and *also*
`numeric_column_not_right_aligned` for col 1, because the cell is
parsed as `none` alignment after the GFM check fails. Table 1 (the
same-shape table with explicit alignments) emits zero findings —
proving the validator does not double-fire on a well-formed table.

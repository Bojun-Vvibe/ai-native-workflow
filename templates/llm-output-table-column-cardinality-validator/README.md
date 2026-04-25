# llm-output-table-column-cardinality-validator

Pure stdlib validator for GFM-style markdown tables emitted by an LLM.
The model loves to say "here is a 4-column table" and then drop a
column in row 7, or split a cell with an unescaped pipe, or forget the
alignment delimiter row entirely. Downstream renderers (most agent
UIs, Slack, GitHub) silently *rewrite* such tables — duplicating
cells, shifting columns, or rendering as paragraph text — so the
operator sees "a table" and never notices the data drift.

Five finding classes:

- **`missing_delimiter`** — row 1 looks like a header but row 2 is not
  a `|---|---|` delimiter line. Most renderers will not render the
  block as a table at all.
- **`column_count_mismatch`** — a body row has a different number of
  cells than the header. Reports `expected` and `actual`.
- **`delimiter_count_mismatch`** — the `---` delimiter row itself has
  a different number of cells than the header.
- **`unescaped_pipe`** — a body row has *exactly* one extra cell vs
  the header AND the literal `|` count is one above the GFM
  expectation, classified as a likely in-cell pipe that needs
  `\|`. Surfaced separately because the fix is at the tokenizer
  layer, not the data layer.
- **`empty_table`** — header + delimiter present but zero body rows.

## When to use

- Post-decode gate on any LLM output that is supposed to contain a
  markdown table — fail fast before the table reaches a renderer or
  a downstream parser that will silently misalign columns.
- CI assertion on captured prompt-replay fixtures — a regression in
  the prompt that drops the delimiter row instructions surfaces as
  `missing_delimiter` going from 0 to N immediately.
- Forensic pass on a single bad output before refiling a bug —
  confirms whether the issue is "model forgot the spec",
  "model has a row it can't fit", or "model put a `|` in a cell".

## When NOT to use

- This is **not** a markdown parser. It walks five structural rules
  only — no inline-link validation, no rendered-width check, no
  alignment-marker semantics (`:---:` is treated identically to
  `---`).
- This is **not** a CSV / TSV validator. The escape character is `\|`
  per GFM, not `""` per RFC 4180.
- It does **not** repair tables. Caller decides whether to fail CI,
  drop the output, or hand it to a separate repair pass.

## Design choices worth knowing

- **`unescaped_pipe` is checked before falling through to
  `column_count_mismatch`.** The two are mutually exclusive in the
  output even though the underlying signal — "row cell count
  drifted" — is the same. The taxonomy distinction matters because
  the *fix* lives in different layers.
- **Findings are sorted `(table_index, row_index, kind)`.** Two runs
  over the same input produce byte-identical output, so cron-driven
  alerting can diff yesterday's report against today's without
  false-positive churn.
- **`_split_row` honors `\|`.** A literal pipe escaped per GFM does
  not contribute to the cell count and does not trip the
  `unescaped_pipe` heuristic — see case 04 row 3 in the worked
  example.
- **No-table input is `ok=True` with `table_count=0`.** A document
  with zero tables has zero table-cardinality bugs by construction,
  and forcing the caller to special-case "empty document" is friction
  for no benefit.

## Composes with

- **`agent-output-validation`** — schema-validate the JSON wrapper of
  the LLM response, then run this on the `markdown_body` field. The
  two layers cover non-overlapping bug classes.
- **`structured-output-repair-loop`** — `column_count_mismatch` and
  `unescaped_pipe` are both repairable; `missing_delimiter` is
  cheaply repairable by inserting the delimiter row.
- **`structured-error-taxonomy`** — every finding maps to
  `attribution=tool` (the LLM emitted bad markdown) and
  `retryability=retry_with_repair` (the prompt is fine; the response
  is fixable).
- **`agent-decision-log-format`** — one log line per `Finding`,
  carrying `kind` and `table_index` so a queryable audit can
  attribute regressions to the exact prompt revision.

## Adapt this section

- `_TABLE_LINE_RE` — relax the leading-`|` requirement if your
  model emits "loose" GFM where the leading and trailing pipes are
  optional (rare but legal in some flavors).
- `unescaped_pipe` heuristic — tighten the heuristic to also fire
  when the row is *missing* one cell (cell containing a literal `|`
  followed by a separator that *was* escaped). Default is
  conservative: only the over-count case fires, because that's the
  one that is unambiguously this bug.

## Worked example

`examples/example.py` runs five synthetic markdown documents — one
clean control plus one for each finding class (the last covering both
`empty_table` and `delimiter_count_mismatch` together) — and prints
one JSON report per document followed by a doc-set tally.

Run from the repo root:

```
python3 templates/llm-output-table-column-cardinality-validator/examples/example.py
```

### Worked example output

```
========================================================================
01 healthy
========================================================================
{
  "finding_kind_totals": {},
  "findings": [],
  "ok": true,
  "table_count": 1,
  "tables": [
    {
      "body_rows": 3,
      "end_line": 7,
      "findings": [],
      "header_columns": 3,
      "start_line": 3,
      "table_index": 0
    }
  ]
}

========================================================================
02 missing_delimiter
========================================================================
{
  "finding_kind_totals": {
    "missing_delimiter": 1
  },
  "findings": [
    {
      "detail": "header row not followed by a `|---|---|` delimiter; most renderers will not render this as a table",
      "kind": "missing_delimiter",
      "row_index": null,
      "table_index": 0
    }
  ],
  "ok": false,
  "table_count": 1,
  "tables": [
    {
      "body_rows": 2,
      "end_line": 5,
      "findings": [
        {
          "detail": "header row not followed by a `|---|---|` delimiter; most renderers will not render this as a table",
          "kind": "missing_delimiter",
          "row_index": null,
          "table_index": 0
        }
      ],
      "header_columns": 3,
      "start_line": 3,
      "table_index": 0
    }
  ]
}

========================================================================
03 column_count_mismatch
========================================================================
{
  "finding_kind_totals": {
    "column_count_mismatch": 1
  },
  "findings": [
    {
      "detail": "row has 3 cells; header expected 4",
      "kind": "column_count_mismatch",
      "row_index": 3,
      "table_index": 0
    }
  ],
  "ok": false,
  "table_count": 1,
  "tables": [
    {
      "body_rows": 3,
      "end_line": 7,
      "findings": [
        {
          "detail": "row has 3 cells; header expected 4",
          "kind": "column_count_mismatch",
          "row_index": 3,
          "table_index": 0
        }
      ],
      "header_columns": 4,
      "start_line": 3,
      "table_index": 0
    }
  ]
}

========================================================================
04 unescaped_pipe
========================================================================
{
  "finding_kind_totals": {
    "unescaped_pipe": 1
  },
  "findings": [
    {
      "detail": "row has 4 cells vs header 3; likely an unescaped `|` inside a cell \u2014 escape as `\\|`",
      "kind": "unescaped_pipe",
      "row_index": 3,
      "table_index": 0
    }
  ],
  "ok": false,
  "table_count": 1,
  "tables": [
    {
      "body_rows": 3,
      "end_line": 7,
      "findings": [
        {
          "detail": "row has 4 cells vs header 3; likely an unescaped `|` inside a cell \u2014 escape as `\\|`",
          "kind": "unescaped_pipe",
          "row_index": 3,
          "table_index": 0
        }
      ],
      "header_columns": 3,
      "start_line": 3,
      "table_index": 0
    }
  ]
}

========================================================================
05 empty_table + delimiter_count_mismatch
========================================================================
{
  "finding_kind_totals": {
    "delimiter_count_mismatch": 1,
    "empty_table": 1
  },
  "findings": [
    {
      "detail": "header + delimiter present but zero body rows",
      "kind": "empty_table",
      "row_index": null,
      "table_index": 0
    },
    {
      "detail": "delimiter row has 2 cells; header has 3",
      "kind": "delimiter_count_mismatch",
      "row_index": 1,
      "table_index": 0
    }
  ],
  "ok": false,
  "table_count": 1,
  "tables": [
    {
      "body_rows": 0,
      "end_line": 4,
      "findings": [
        {
          "detail": "delimiter row has 2 cells; header has 3",
          "kind": "delimiter_count_mismatch",
          "row_index": 1,
          "table_index": 0
        },
        {
          "detail": "header + delimiter present but zero body rows",
          "kind": "empty_table",
          "row_index": null,
          "table_index": 0
        }
      ],
      "header_columns": 3,
      "start_line": 3,
      "table_index": 0
    }
  ]
}

========================================================================
summary
========================================================================
{
  "finding_kind_totals_across_docs": {
    "column_count_mismatch": 1,
    "delimiter_count_mismatch": 1,
    "empty_table": 1,
    "missing_delimiter": 1,
    "unescaped_pipe": 1
  }
}
```

Notice case 04 row 3 — the row `| pro | basic | advanced features | $29 |`
trips `unescaped_pipe` (the in-cell `|` between `basic` and
`advanced`), while row 4 `| ent | escaped \| inside cell is fine | $999 |`
correctly does *not* fire because the `\|` is honored. This is the
exact discrimination the five-rule taxonomy is designed to give you:
"row cell count drifted" is a generic symptom; the underlying cause
splits across at least three different fix sites.

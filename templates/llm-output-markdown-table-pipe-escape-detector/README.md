# llm-output-markdown-table-pipe-escape-detector

Detects markdown pipe-table rows where a `|` inside a cell has not been
escaped as `\|`, causing the row to split into more "columns" than the
header declared.

## Why it matters

Pipe tables are GFM's column separator. Unescaped pipes inside cells are a
common LLM failure mode in three flavors:

1. **Type unions** — `int | str`, `Result | Error`
2. **Shell pipelines** — `cat foo | grep bar`
3. **Regex alternation** — `'foo|bar'`

Renderers silently re-tabulate the row, which:
- shifts the visible column boundaries
- can drop content past the original last column
- breaks downstream parsers that expect a fixed cardinality

## Heuristic

For each table:
1. Find a header line followed by a separator line (`|---|---|...`).
2. Count unescaped pipes (`(?<!\\)\|`) in the header — this is the expected
   per-row count.
3. Flag any data row whose unescaped pipe count differs.

This is intentionally a count-based heuristic, not a full parser — it
catches the high-signal cases without false-positiving on indented code
inside tables.

## Usage

```
python3 detector.py <file> [<file>...]
```

Exits 0 clean, 1 on hits, 2 on bad usage.

## Worked example

Input `worked-example.txt`:

```
## Type union examples

| Name  | Type      | Notes                       |
|-------|-----------|-----------------------------|
| id    | int       | primary key                 |
| value | int | str | union of int and string     |
| query | str       | grep -E 'foo|bar' style     |
| good  | str       | escaped pipe \| works fine  |

End of table.
```

Real run:

```
$ python3 detector.py worked-example.txt
worked-example.txt:6: table row has 5 unescaped pipes, header has 4 (diff +1) -- likely missing \| escape
    row: '| value | int | str | union of int and string     |'
worked-example.txt:7: table row has 5 unescaped pipes, header has 4 (diff +1) -- likely missing \| escape
    row: "| query | str       | grep -E 'foo|bar' style     |"

FAIL: 2 table row(s) with pipe-count mismatch
```

Exit code: `1`.

The "good" row on line 8 uses `\|` and is correctly ignored.

## Remediation

Two options for the LLM/post-processor:

1. **Escape literal pipes**: replace `|` with `\|` inside detected cells.
2. **Switch syntax**: render type unions as `Union[int, str]` and shell
   pipelines as inline code spans surrounded by backticks; pipes inside
   inline code are still parsed as separators by some renderers, so prefer
   option 1 when in doubt.

## Known limits

- Inline code spans containing `|` are not specially handled; the
  detector treats them by raw pipe count. If your renderer ignores pipes
  inside backticks, this can produce false positives — flag-gate or
  preprocess if needed.
- Tables with fewer than two rows (header + separator only) are skipped.

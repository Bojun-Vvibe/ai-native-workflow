# llm-output-markdown-table-column-count-consistency-detector

Flags GitHub-flavored markdown tables whose body rows have a column
count that does not match the header row's column count. Also flags
the separator row when its cell count differs from the header.

## What it detects

A GFM table where header, separator, and body rows must all share
the same number of cells:

```
| name | role | team |
| ---- | ---- | ---- |
| ada  | eng  | core |
| bob  | pm   |              <-- 2 cells, header has 3
| cid  | eng  | core | x |   <-- 4 cells, header has 3
```

Most renderers silently pad or drop cells, so the table appears to
work — but the rendered output disagrees with the author's intent
and downstream tools (CSV export, prettier) reflow inconsistently.

It is **code-fence aware**: rows inside fenced code blocks (``` or
~~~) are ignored. It also **respects escaped pipes** (`\|`) inside
cells, so inline code like `` `a \| b` `` is counted as one cell.

## Why it matters for LLM-generated markdown

- LLMs frequently emit tables where the body width drifts from the
  header — especially when a row has a long cell that the model
  thinks it can collapse into one fewer column.
- A formatter (prettier, mdformat) will normalize cell counts by
  padding with empty cells, producing noisy diffs on otherwise
  content-only PRs.
- Downstream tooling (CSV/JSON conversion, table-to-data pipelines)
  silently drops trailing data or shifts columns when widths drift.

## Usage

```
python3 detect.py path/to/file.md
```

## Exit codes

| code | meaning              |
| ---- | -------------------- |
| 0    | no findings          |
| 1    | findings on stdout   |
| 2    | usage / read error   |

Output format:
`<file>:<line>: <message>: <raw line>`

## Worked example

Run against `examples/bad.md`:

```
$ python3 detect.py examples/bad.md
examples/bad.md:8: body row has 2 cells, header has 3: | bob  | pm   |
examples/bad.md:9: body row has 4 cells, header has 3: | cid  | eng  | core | extra |
examples/bad.md:14: separator row has 3 cells, header has 2: | --- | ---  | ---  |
examples/bad.md:16: body row has 3 cells, header has 2: | b   | 2    | 3    |
$ echo $?
1
```

Run against `examples/good.md`:

```
$ python3 detect.py examples/good.md
$ echo $?
0
```

The bad file produces 4 findings across two tables; the table inside
the fenced code block is correctly ignored. The good file confirms
escaped pipes (`\|`) inside inline code do not break cell counting.

# llm-output-csv-inconsistent-column-count-detector

Detects rows in CSV output whose field count differs from the header.

LLMs commonly drift CSV shape between rows:

- An extra trailing comma → row has **+1** field.
- A free-text cell with an unescaped comma → row has **+N** fields.
- A missing value with no placeholder → row has **−1** field.
- A model "summarizing" a row with prose → row has **−many** fields.

These break every downstream consumer (pandas `read_csv`, `csv.DictReader`,
SQL `COPY`, BigQuery loader, etc.) and often only fail at row 47 of 10,000.

## Usage

```sh
python3 detector.py < input.csv
```

The first non-empty line is treated as the header. The detector parses with
Python's stdlib `csv.reader` (default dialect, so quoted commas are handled
correctly). It then reports each row whose field count diverges:

```
row=<N> expected=<H> actual=<A> first_field=<repr>
```

`total_findings` and `header_columns` are printed on stderr. Exit code is
always 0 (advisory).

## Worked example

```sh
$ python3 detector.py < bad.txt
row=3 expected=4 actual=5 first_field='2'
row=4 expected=4 actual=3 first_field='3'
row=5 expected=4 actual=6 first_field='4'
# stderr: total_findings=3
#         header_columns=4

$ python3 detector.py < good.txt
# stderr: total_findings=0
#         header_columns=4
```

## Why this matters for LLM output

Most CSV consumers fail loudly *only* on the first bad row, so:

- A 10k-row dump can hide a single row with a stray comma until import.
- The `csv` module *does* tolerate ragged rows silently in some modes — your
  downstream may quietly drop or shift columns instead of erroring.
- Re-asking the LLM to "regenerate" tends to introduce *different* drift.

Run this detector before handing CSV to any importer. It is stdlib-only and
respects standard quoting rules (i.e., `"a,b",c` is correctly parsed as 2
fields, not 3).

## Limits

- Assumes the first non-empty row is the header. If your CSV has no header,
  pre-pend a synthetic one or modify the script to use the first data row's
  width as the expected width.
- Uses the default `csv` dialect. For TSV / pipe-separated input, change the
  `csv.reader` call accordingly.
- Does not detect *type* drift inside a column — only *count* drift.

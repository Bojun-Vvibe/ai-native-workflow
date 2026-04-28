# llm-output-jsonl-mixed-schema-detector

Pure-stdlib, code-fence-aware detector that catches **schema drift
across records** in JSONL (newline-delimited JSON) blocks an LLM
emits in markdown.

JSONL is a streaming format. Downstream consumers (Spark, DuckDB
`read_json_auto`, BigQuery, pandas `read_json(lines=True)`) infer a
single schema from the first batch of records and then either
reject — or, worse, silently null out — fields that show up later.
LLMs that are asked for "20 sample rows" routinely produce:

```jsonl
{"id": 1, "name": "alice", "email": "a@x"}
{"id": 2, "name": "bob"}
{"id": 3, "full_name": "carol", "email": "c@x"}
```

Three different schemas in three rows. The bug is invisible to the
model because it has no consumer in the loop. This detector flags
it at emit time so the output can be re-prompted before it's loaded
anywhere.

## What it flags

| kind | meaning |
|---|---|
| `schema_drift` | top-level key-set differs from the baseline (the first valid object record). `extra=` lists keys present here but not in the baseline; `missing=` lists baseline keys absent here |
| `not_object` | the line parsed as JSON but is not an object (e.g. a bare array or scalar). JSONL records are conventionally objects |
| `invalid_json` | the line could not be parsed as JSON at all |

Recognized fence info-string tags: `jsonl`, `ndjson`, `json-lines`,
`jsonlines` (case-insensitive).

## Out of scope (deliberately)

- Nested-schema comparison (only top-level keys are inspected).
- Type comparison of values for the same key.
- Key-case mismatches beyond the exact-string set difference.
- Full JSON Schema validation. This is a *first-line-defense* sniff
  test, not a schema validator.

## Usage

```
python3 detect.py <markdown_file>
```

Stdout: one finding per line, e.g.

```
block=1 line=3 kind=schema_drift extra=full_name missing=name
```

Stderr: `total_findings=<N> blocks_checked=<M>`.

Exit codes:

| code | meaning |
|---|---|
| `0` | no findings |
| `1` | at least one finding |
| `2` | bad usage |

## Worked example

Run against the bundled `examples/bad.md` (5 findings: 3 schema
drifts, 1 invalid JSON, 1 non-object) and `examples/good.md` (0
findings):

```
$ python3 detect.py examples/bad.md
block=1 line=2 kind=schema_drift extra=- missing=email
block=1 line=3 kind=schema_drift extra=full_name missing=name
block=1 line=4 kind=schema_drift extra=age missing=-
block=2 line=2 kind=invalid_json
block=2 line=3 kind=not_object
# stderr: total_findings=5 blocks_checked=2
# exit: 1

$ python3 detect.py examples/good.md
# stderr: total_findings=0 blocks_checked=2
# exit: 0
```

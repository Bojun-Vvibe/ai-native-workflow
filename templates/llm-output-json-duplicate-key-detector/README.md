# llm-output-json-duplicate-key-detector

Pure stdlib detector that scans a JSON document produced by an LLM
for duplicate member names *at the same object scope*. RFC 8259 says
duplicate names "SHOULD be unique" and that behaviour is undefined
otherwise — every popular consumer made a different choice, and the
LLM that emitted the doc cannot see the disagreement. This detector
catches the smell before the doc is fanned out to consumers that
silently disagree.

## Why a separate template

JSON output siblings cover adjacent concerns:

- `llm-output-json-trailing-comma-and-comment-detector` — *grammar*
  bugs (`{"a":1,}`, `// comment`). A duplicate-key doc parses fine
  for every consumer; that detector will not catch it.
- `llm-output-jsonschema-repair` — schema *fit*. Both occurrences of
  the duplicated key satisfy the schema, so the schema repairer
  passes the doc through.
- `partial-json-streaming-parser`, `partial-json-tail-recovery` —
  recover from truncation. Duplicate-key docs are not truncated.
- `json-schema-required-field-coverage-reporter` — reports which
  required fields are missing. Required fields are present here —
  twice.

## What it catches

| kind | what it catches |
|---|---|
| `duplicate_key` | the same member name appears more than once inside the same object scope; nested scopes and sibling scopes are tracked independently |

For three-way duplicates (`{"k":1,"k":2,"k":3}`) the detector emits
*two* findings — one for each redundant occurrence — both pointing
at the original line.

## Why parser disagreement matters

The same JSON, fed to four common consumers, lands on four different
values for the duplicated key:

- Python `json.loads` — keeps the **last** value
- JavaScript `JSON.parse` — keeps the **last** value
- Go `encoding/json` — keeps the **last** value, but `json.RawMessage`
  round-trips both occurrences
- Ruby `JSON.parse` — keeps the **first** in some versions, the
  **last** in others

If a Python ingest job and a Ruby publishing job both consume the
same doc, they will silently store different values. The model
never sees the divergence. The pipeline does not raise. Only a
detector at emit-time catches it.

## Design choices

- **Hand-written tokeniser.** `json.loads` collapses duplicates
  before the caller can see them, so it cannot be used. The
  tokeniser walks one character at a time, tracks a stack of
  `(is_object, key_set)` frames, and records the first line each
  key appears in per-frame.
- **Stops on grammar errors.** Unterminated strings or mismatched
  braces stop the walk and return whatever was found so far —
  grammar validation is `llm-output-json-trailing-comma-and-comment-detector`'s
  job, not this one's.
- **Same key in sibling scopes is fine.** `{"a":{"x":1},"b":{"x":2}}`
  reports zero findings — `x` lives in two separate scopes. The
  duplicate must be in the same `{...}` to count.
- **Deterministic order.** Findings are sorted by
  `(line_no, col_no, key)`. Two runs on the same input produce
  byte-identical output.
- **Pure function.** `detect(src) -> JsonDupKeyReport`. No I/O, no
  clocks, no transport.
- **Stdlib only.** `dataclasses`, `json` (only for serialising the
  report), `sys`. No `re`, no third-party JSON parser.

## Composition

- `llm-output-json-trailing-comma-and-comment-detector` — run first;
  if grammar is broken this detector's results are partial.
- `llm-output-jsonschema-repair` — run *after* this detector. A
  duplicate-key doc that passes schema repair is still wrong.
- `structured-error-taxonomy` — `duplicate_key` is
  `attribution=model`, `severity=error` for any pipeline that fans
  the doc to two or more consumers (because they will disagree),
  `severity=warning` for single-consumer pipelines.
- `prompt-template-versioner` — when this detector starts firing on
  a previously-clean prompt, the version diff is the smoking gun.

## Worked example

Run `python3 example.py` from this directory. Seven cases — two
clean (flat + nested), four flavours of duplicate, and one case
showing that the same key in sibling scopes is *not* a finding.

```
$ python3 example.py
# llm-output-json-duplicate-key-detector — worked example

## case 01_clean_flat
{ "ok": true, "scopes_checked": 1, "keys_checked": 3, "findings": [] }

## case 02_clean_nested
{ "ok": true, "scopes_checked": 2, "keys_checked": 4, "findings": [] }

## case 03_dup_top_level
{ "findings": [{"kind":"duplicate_key","key":"id","line_no":4,...}], "ok": false }

## case 04_dup_in_nested
{ "findings": [{"kind":"duplicate_key","key":"name",...}], "ok": false }

## case 05_dup_inside_array_of_objects
{ "findings": [{"kind":"duplicate_key","key":"k",...}], "ok": false }

## case 06_same_key_diff_scopes_is_clean
{ "ok": true, "scopes_checked": 3, "keys_checked": 4, "findings": [] }

## case 07_three_way_dup
{ "findings": [
    {"kind":"duplicate_key","key":"flag",...},
    {"kind":"duplicate_key","key":"flag",...}
  ], "ok": false }
```

Read across the cases: 01 and 02 are both clean — flat object and
nested object plus array. 03 catches the most common bug — the
model regenerates a key it already emitted. 04 is the same bug
inside a nested object — sibling scope tracking is required. 05
catches duplicates inside an array element; the array does not
introduce a new key scope but each `{...}` inside it does. 06 is
the load-bearing negative case — `x` appears in two different
objects and is *not* a finding. 07 shows that a three-way duplicate
emits two findings (one per redundant occurrence), so the report
size scales with severity.

The output is byte-identical between runs — `_CASES` is a fixed
list, the checker is a pure function, and findings are sorted by
`(line_no, col_no, key)` before serialisation.

## Exit codes

- `0` — all cases clean.
- `1` — at least one case produced findings (the demo intentionally
  exercises every duplicate flavour, so a normal run exits 1).

When wired into CI as a pre-commit / pre-publish hook, exit 1 means
"reject the document until duplicate keys are removed and the model
is asked which value it actually meant."

## Files

- `example.py` — the checker + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.

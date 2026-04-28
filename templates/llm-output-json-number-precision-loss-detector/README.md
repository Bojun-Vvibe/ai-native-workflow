# llm-output-json-number-precision-loss-detector

Pure stdlib detector that scans a JSON document for numeric literals
that will lose precision the moment they are consumed by an
IEEE-754-double-only consumer (JavaScript `JSON.parse`, jq, most
browser code, many SQL JSON columns, every Postgres `jsonb` numeric).

The failure mode it catches: the LLM emits a JSON doc with an
integer ID like `{"id": 9007199254740993}` (= 2^53 + 1). Python's
`json.loads` parses it as a Python `int` and round-trips it
perfectly. The same bytes shipped to a Node.js service round-trip
as `9007199254740992` — the trailing `3` becomes `2` because
`Number.MAX_SAFE_INTEGER == 2^53 - 1`. Two services now disagree on
the user's ID and downstream joins silently lose rows.

## Why a separate template

JSON output siblings cover adjacent concerns:

- `llm-output-json-trailing-comma-and-comment-detector` — *grammar*
  bugs. A precision-loss doc parses cleanly; that detector will not
  fire.
- `llm-output-json-duplicate-key-detector` — same-scope duplicate
  member names. Orthogonal.
- `llm-output-jsonschema-repair` — schema *fit*. The number is
  still a valid `integer`; schema repair passes the doc through.
- `llm-output-numeric-hallucination-detector` — semantic accuracy of
  numbers (does the model invent figures). This detector ignores
  semantics — it only cares about wire-format precision.

## What it catches

| kind | what it catches |
|---|---|
| `int_unsafe` | integer literal outside `[-2^53+1, 2^53-1]`; `JSON.parse` and jq silently round to nearest double |
| `float_overflow` | float literal whose magnitude exceeds the IEEE-754 double finite max (~1.798e308); becomes `Infinity` |
| `float_underflow` | float literal that parses to exactly 0.0 despite having non-zero digits in the source; lost magnitude |
| `float_precision_loss` | float with more than 17 significant digits whose `repr` does not round-trip the original literal |

## Why parser disagreement matters

A Python ingest job stores `id=9007199254740993` exactly. The same
JSON, fanned out to a Node analytics worker, stores
`id=9007199254740992`. A subsequent join from the analytics worker
back to the source-of-truth row returns zero matches — the row is
"missing" from every dashboard, even though the database has it.
The model never sees the divergence. The pipeline does not raise.
Only an emit-time detector catches it.

## Design choices

- **Hand-written tokeniser.** CPython's `json.loads` parses huge
  ints losslessly into Python's arbitrary-precision `int`, hiding
  the smell from any post-parse check. The tokeniser walks one
  character at a time, skips strings (so numbers embedded in string
  values are correctly ignored), and only classifies number
  literals.
- **Strict significant-digit count.** Significant digits = total
  digit chars after stripping leading zeros. `0.12345678901234567890`
  has 20 sig digits; the IEEE-754 double "round-trip safe" budget is
  17. We only flag when round-trip via `repr` *also* fails — so
  `0.1` (which has 17-ish bits of error but is a canonical literal)
  does not fire.
- **Strings are opaque.** The string scanner skips backslash escapes
  carefully so a JSON like `{"note": "id is 9007199254740993"}`
  reports zero findings. This is the load-bearing negative case.
- **No grammar validation.** A broken JSON doc is the
  trailing-comma detector's job; this one returns whatever it found
  before the break.
- **Deterministic order.** Findings are sorted by
  `(line_no, col_no, kind)`. Two runs on the same input produce
  byte-identical output.
- **Pure function.** `detect(src) -> JsonNumberPrecisionReport`. No
  I/O, no clocks, no transport.
- **Stdlib only.** `dataclasses`, `json` (only for serialising the
  report), `sys`. No `re`, no third-party JSON or numeric library.

## Composition

- `llm-output-json-trailing-comma-and-comment-detector` — run first;
  if grammar is broken this detector's results are partial.
- `llm-output-json-duplicate-key-detector` — orthogonal; run both
  on the same doc as a battery.
- `llm-output-jsonschema-repair` — a precision-lossy doc still
  passes schema repair, so this detector covers a gap that schema
  repair does not.
- `structured-error-taxonomy` — all four kinds are
  `attribution=model`. `int_unsafe` and `float_overflow` are
  `severity=error` (silent data corruption downstream).
  `float_underflow` and `float_precision_loss` are `severity=error`
  for financial / scientific pipelines, `severity=warning` for
  display-only pipelines.
- `prompt-template-versioner` — when this detector starts firing
  on a previously-clean prompt, the version diff is the smoking
  gun (e.g. the model started emitting raw IDs instead of stringified
  IDs).
- One common upstream fix is to teach the prompt to emit large IDs
  as strings: `{"id": "9007199254740993"}`. This detector then
  passes — strings are opaque to numeric checks.

## Worked example

Run `python3 example.py` from this directory. Nine cases — two
clean (small ints, normal floats), four flavours of finding, one
mixed doc with both clean and bad numbers, and the load-bearing
"number embedded in a string is ignored" case.

```
$ python3 example.py
# llm-output-json-number-precision-loss-detector — worked example

## case 01_clean_small_ints
{ "ok": true, "numbers_checked": 3, "findings": [] }

## case 02_clean_normal_floats
{ "ok": true, "numbers_checked": 3, "findings": [] }

## case 03_int_above_safe
{ "findings": [{"kind":"int_unsafe","literal":"9007199254740993",...}], "ok": false }

## case 04_int_far_below_safe
{ "findings": [{"kind":"int_unsafe","literal":"-18014398509481984",...}], "ok": false }

## case 05_float_overflow
{ "findings": [{"kind":"float_overflow","literal":"1e400",...}], "ok": false }

## case 06_float_underflow
{ "findings": [{"kind":"float_underflow","literal":"1e-400",...}], "ok": false }

## case 07_float_precision_loss
{ "findings": [{"kind":"float_precision_loss","literal":"0.12345678901234567890",...}], "ok": false }

## case 08_mixed_clean_and_bad
{ "findings": [
    {"kind":"float_overflow","literal":"1e500",...},
    {"kind":"int_unsafe","literal":"9999999999999999",...}
  ], "ok": false }

## case 09_negative_in_string_is_ignored
{ "ok": true, "numbers_checked": 0, "findings": [] }
```

Read across the cases: 01 is the boundary — `9007199254740991` is
exactly `2^53 - 1`, the largest safe integer, and is *not* a
finding. 02 is normal scientific floats — none lose precision. 03
adds 2 to that boundary and trips `int_unsafe`. 04 catches the
negative side. 05 and 06 are the magnitude-edge cases —
`1e400` overflows to infinity, `1e-400` underflows to zero. 07 is
the subtlest — the literal parses to a finite normal double, but
the round-tripped value differs from the source bytes in the
trailing digits. 08 confirms the detector finds *all* bad numbers
in a multi-line doc. 09 is the load-bearing negative — a
precision-busting integer embedded inside a string value is
correctly ignored, because emitting IDs as strings is the canonical
fix and we must not fight it.

The output is byte-identical between runs — `_CASES` is a fixed
list, the checker is a pure function, and findings are sorted by
`(line_no, col_no, kind)` before serialisation.

## Exit codes

- `0` — all cases clean.
- `1` — at least one case produced findings (the demo intentionally
  exercises every finding kind, so a normal run exits 1).

When wired into CI as a pre-commit / pre-publish hook, exit 1 means
"reject the document until numbers are reformatted as strings or
the prompt is fixed."

## Files

- `example.py` — the checker + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.

# llm-output-maxima-ev-detector

Static detector for **dynamic-evaluation sinks** in Maxima script files (`.mac`, `.mc`, `.maxima`, `.max`) that an LLM may emit when wiring up "let the user define their own formula", "load this generated worksheet", or "evaluate the integral the user typed".

## Problem

Maxima is a computer-algebra system, but it ships with a small, sharp eval-of-string surface. Each of the following turns user-controlled text into evaluated Maxima code:

| Sink | What it does |
|------|--------------|
| `ev(EXPR, ...)` | Re-evaluate `EXPR` with extra bindings/flags. When `EXPR` was itself built at runtime (e.g. via `parse_string`), this is the second half of an eval-of-string. |
| `eval_string("...")` | Parse a Maxima string into a form **and** evaluate it. The textbook one-call eval-of-string. |
| `parse_string("...")` | Parse-only sibling of `eval_string`. Pairs with `ev()` to RCE; flagged because the parsed form will almost always be evaluated. |
| `batch(EXPR)` | Read a `.mac` file and execute it. Dynamic path = RCE. |
| `batchload(EXPR)` | Quieter sibling of `batch`. Same RCE shape. |
| `load(EXPR)` | Load a Maxima/Lisp package. `load(draw)` (bareword) and `load("pkg.lisp")` (string literal) are idiomatic and safe; `load(varexpr)` is dynamic. |

LLMs reach for `ev(parse_string(user_input))` or `eval_string(user_input)` the moment a prompt mentions "evaluate the formula the user typed". The result is a Maxima session that will happily execute `system("...")`, write files, or `kill(all)$`.

## What the detector flags

- `ev-call`             - `ev(...)` (any argument)
- `eval-string-call`    - `eval_string(...)` (any argument)
- `parse-string-call`   - `parse_string(...)` (any argument)
- `batch-dynamic`       - `batch(EXPR)` where `EXPR` is **not** a single string literal
- `batchload-dynamic`   - `batchload(EXPR)` where `EXPR` is **not** a single string literal
- `load-dynamic`        - `load(EXPR)` where `EXPR` is **not** a single string literal **and not** a single bareword (so `load(draw)` and `load("pkg.lisp")` pass; `load(varname)` and `load(sconcat(...))` are flagged)

## What it deliberately does NOT flag

- Any sink mention inside a `/* ... */` block comment.
- Any sink mention inside a `"..."` string body (the body is masked before regex matching).
- `batch("plot.mac")` / `batchload("init.mac")` - static literal path.
- `load("draw")` / `load(draw)` / `load(diff)` - the canonical "load this package" idiom.

### Known limitation

`load(varname)` *is* flagged because `load` accepts paths too, but `load(draw)` is allowed as the canonical bareword form. We cannot distinguish "bareword that names a package" from "bareword that is a runtime variable holding a path" without a symbol table; the rule errs toward the idiomatic bareword being safe and forces the dynamic form to use a non-bareword expression (e.g. `load(sconcat(...))`).

## How it works

Single pass, python3 stdlib only (`detector.py`). The `mask()` function blanks Maxima `/* ... */` block comments and `"..."` string bodies while preserving newlines so reported line numbers stay accurate. After masking, simple call-site regexes (`ev(`, `eval_string(`, `parse_string(`) fire on first match per line; the `batch` / `batchload` / `load` arms additionally extract the first call argument with a paren-balanced scan and inspect it against the static-arg predicate.

## Usage

```sh
python3 detector.py path/to/worksheets/ session.mac
```

Exit code `1` if any finding is emitted, `0` otherwise - drop straight into pre-commit / CI.

## Live smoke test

```
$ bash verify.sh
== bad/ ==
bad/01_ev_call.mac:3:10: parse-string-call parsed : parse_string(formula);
bad/01_ev_call.mac:4:10: ev-call result : ev(parsed, x = 4);
bad/02_eval_string.mac:3:1: eval-string-call eval_string(expr);
bad/03_parse_string.mac:3:8: parse-string-call form : parse_string(src);
bad/04_batch_dynamic.mac:3:1: batch-dynamic batch(script_path);
bad/05_batchload_dynamic.mac:3:1: batchload-dynamic batchload(init_file);
bad/06_load_dynamic.mac:2:1: load-dynamic load(sconcat("addons/", plugin, ".lisp"));
== good/ ==
-- summary --
bad-findings:  7  (expected: >= 6)
good-findings: 0 (expected: 0)
PASS
```

The `good/` corpus exercises every false-positive trap: comments-only mentions, string-body mentions, static literal `batch` / `batchload` paths, and idiomatic bareword / literal `load` forms.

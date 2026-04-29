# llm-output-common-lisp-eval-detector

## Purpose

Detect Common Lisp dynamic-evaluation calls that take a runtime form
or string and execute it.

The flagged primitives are:

- `(eval FORM)` — evaluate a Lisp form in the null lexical environment.
- `(read-from-string STR)` — parse a string into an S-expression. Almost
  always paired with `eval` to "run a string of Lisp", which is
  arbitrary code execution.
- `(compile nil FORM)` — compile then return a function. When `FORM`
  comes from user input, this is `exec()` on a string.
- `(load FILE)` — load a Lisp source file. When `FILE` is influenced by
  user input, attackers can pull in arbitrary code.

LLMs reach for these constantly when asked to build a "REPL", a "rule
engine", or a "config DSL", because they treat S-expressions as inert
data. They aren't.

## When to use

- Reviewing LLM-generated Common Lisp before merging.
- CI lint over `*.lisp`, `*.lsp`, `*.cl`, `*.asd` files.
- Pre-commit lint on agent-authored Lisp.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> \u2014 <snippet>`.

## What it flags

- `cl-eval`              — `(eval ...)`, `(cl:eval ...)`, `(common-lisp:eval ...)`
- `cl-read-from-string`  — `(read-from-string ...)` and package-qualified variants
- `cl-compile`           — `(compile nil ...)` (the runtime-compile-a-form form)
- `cl-load`              — `(load ...)`

## What it intentionally skips

- `;` line comments.
- Contents of `"..."` string literals (with `\\` escape handling).
- Contents of `#| ... |#` block comments (nesting tracked).
- `(compile FOO ...)` where `FOO` is a symbol — that's the
  ahead-of-time form for a named function, not the dangerous one.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — Lisp files that MUST trigger.
- `good/` — Lisp files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Example output

```
$ python3 detect.py bad/
bad/01_eval.lisp:3:1: cl-eval \u2014 (eval (read-from-string user-input))
...
# 7 finding(s)
```

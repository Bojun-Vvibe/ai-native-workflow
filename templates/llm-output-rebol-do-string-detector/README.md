# llm-output-rebol-do-string-detector

## Purpose

Detect Rebol/Red `do STRING` and related dynamic-evaluation patterns.

In Rebol and Red, `do` is the universal evaluator. When called on a
string, a braced multi-line string, a `load`-ed string, a `to-block`
result, or a script file path, it loads + executes that input as
Rebol/Red code. The full language is reachable from the evaluated
input — including `delete`, `write`, `call`, `read`, etc. — so any
user-influenced argument is arbitrary code execution.

LLM-emitted Rebol/Red reaches for `do STRING` whenever the model needs
a "config language", a "rule engine", or a "tiny REPL", because the
homoiconic feel makes it look safe. It is not.

## When to use

- Reviewing LLM-generated Rebol/Red snippets before merging.
- CI lint over `*.r`, `*.r3`, `*.reb`, `*.red` files.
- Pre-commit lint on agent-authored Rebol/Red.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> \u2014 <snippet>`.

## What it flags

- `rebol-do-string`   — `do "..."` (string literal eval)
- `rebol-do-brace`    — `do {...}` (braced multi-line string eval)
- `rebol-do-file`     — `do %script.r` (script-file eval)
- `rebol-do-load`     — `do load ...` (load-then-eval composition)
- `rebol-do-to-block` — `do to-block ...` (string-to-code composition)
- `rebol-load-then-do` — bare `load "..."` (almost always followed by `do`)

## What it intentionally skips

- `;` line comments.
- Contents of `"..."` string literals (with `^` caret-escape handling).
- Contents of `{...}` braced multi-line string literals (nesting tracked).
- Words that merely contain `do` as a substring (`redo`, `do-all`,
  `do-thing`) — only the bare word `do` followed by an evaluated arg
  triggers, via a leading-character allow-list.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — Rebol files that MUST trigger.
- `good/` — Rebol files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Example output

```
$ python3 detect.py bad/
bad/01_do_string.r:3:1: rebol-do-string \u2014 do "print 1 + 1"
...
# 7 finding(s)
```

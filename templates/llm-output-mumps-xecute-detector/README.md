# llm-output-mumps-xecute-detector

Single-pass python3-stdlib scanner that flags MUMPS / M / Caché ObjectScript
dynamic-string-eval sinks in LLM-emitted MUMPS code (`*.m`, `*.mac`, `*.int`,
`*.cos`).

## What it flags

MUMPS has two canonical "compile and run a string at runtime" sinks, plus
the indirection operator that achieves the same thing in expression
position:

* `XECUTE expr` (and its abbreviation `X expr`) — takes a string,
  compiles it as MUMPS source, and runs it inline in the current
  symbol-table scope. This is the MUMPS equivalent of Python `exec()`.
* `@expr` — name-indirection operator. `S @x=1` writes to the variable
  *named by the value of `x`*, `D @x` calls the routine *named by the
  value of `x`*, `G @x` jumps to the label *named by the value of `x`*.
  When `x` is user-controlled, this is dynamic-name code injection.
* `$TEXT(@x)` and `$$@x()` are special cases of the same hazard
  (function-name and routine-text indirection).

## Why this matters

`XECUTE` and `@` are how legacy clinical, financial, and trading MUMPS
codebases implement "configurable" behaviour — a config value names a
routine, a tag, or a whole snippet of M source, and the dispatcher
runs it. LLMs reach for `XECUTE` whenever asked to "make this
extensible," and the generated code almost never validates the
indirection target. In a globals-backed environment, that is RCE
against a database that typically holds PII.

## What is masked before scanning

* `;` line comments (everything from `;` to end of line).
* `"..."` string literals (MUMPS escapes `"` by doubling: `""` inside
  a string is a literal quote, not a terminator).

MUMPS commands and intrinsic names are case-insensitive; the regexes
use `re.IGNORECASE`.

## Suppression

A trailing `;xecute-ok` comment on the same line suppresses every
finding on that line. Use sparingly and never on user-tainted input.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` if any findings, `0` otherwise. Recurses into
directories looking for `*.m`, `*.mac`, `*.int`, `*.cos`.

## Worked example

```
$ python3 detect.py examples/bad
examples/bad/01_xecute_user_input.m:3:2: xecute — X CMD
examples/bad/02_indirection_set.m:3:2: indirection — S @VAR=42
examples/bad/03_xecute_concat.mac:3:2: xecute — XECUTE "S X="_VAL
# 3 finding(s)

$ python3 detect.py examples/good
# 0 finding(s)
```

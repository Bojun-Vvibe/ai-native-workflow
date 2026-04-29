# llm-output-m4-esyscmd-detector

Detect shell-out and dynamic-evaluation sinks in GNU `m4` input.

## Why

`m4` is a macro processor that ships several builtins which hand a
string to `/bin/sh` or re-enter the m4 expander on a string value.
LLM-generated `configure.ac`, autoconf fragments, and ad-hoc m4
scripts reach for these builtins liberally, often interpolating
macro arguments straight into the shell. The most dangerous are:

* `syscmd(...)`     -- run shell command, exit status only
* `esyscmd(...)`    -- run shell command, expand to its stdout
* `eval(...)`       -- evaluate an integer expression (less severe)
* `dnl`-stripped `define(...,esyscmd(...))` patterns at top of file

When the argument is built from `$1`, `$@`, or another macro
expansion rather than a bare string literal, you have a textbook
command-injection sink.

## What this flags

After blanking comments (`dnl ...EOL` and `# ...EOL`) and string
contents (m4 quoted strings written as `` `...' `` -- a backtick
opens, an apostrophe closes, with nesting):

| Pattern                    | Kind                       |
| -------------------------- | -------------------------- |
| `syscmd(<arg>)`            | `m4-syscmd`                |
| `esyscmd(<arg>)`           | `m4-esyscmd`               |
| `eval(<arg>)`              | `m4-eval` (info-level)     |
| `__file__`-level `include(<arg>)` where arg has macro refs | `m4-include-dynamic` |

A finding is upgraded with `-dynamic` suffix if the argument, after
scrubbing, is anything other than an empty `` `' `` literal pair.

## Suppression

Append `dnl m4-exec-ok` to the line.

## Usage

    python3 detector.py <file_or_dir> [...]

Recurses into directories looking for `*.m4`, `*.ac`, `*.am`,
`configure.ac`, `aclocal.m4`. Exit 1 if findings, 0 otherwise.
python3 stdlib only.

## Exit codes

* `0` -- no findings
* `1` -- one or more findings
* `2` -- usage error

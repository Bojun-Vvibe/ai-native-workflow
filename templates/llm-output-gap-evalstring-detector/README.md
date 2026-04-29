# llm-output-gap-evalstring-detector

Single-pass detector for **GAP `EvalString(...)` and
`ReadAsFunction(InputTextString(...))`** runtime
code-evaluation sinks.

## Why this exists

GAP (Groups, Algorithms, Programming) is a computer-algebra
language widely used in mathematics. Its standard library exposes:

```gap
EvalString( str );          # parse + run a GAP expression
EvalString( str, scope );   # same, with a binding scope
```

which evaluates `str` at runtime inside the live workspace. The
result has full access to the session's bindings, the OS-facing
functions (`Exec`, `IO_*`, `Filename`), and any loaded packages.

A close cousin worth flagging is the read-string idiom:

```gap
ReadAsFunction( InputTextString( src ) )
```

This compiles `src` as a function body and returns it; calling the
result executes arbitrary GAP code, equivalent in power to
`EvalString` but spelled differently.

Whenever the source argument is anything other than a manifest,
audited literal, the program is loading code chosen at runtime
from data that may be attacker-controllable: a workspace file, a
network response, a notebook cell, a package fixture.

LLM-emitted GAP code reaches for `EvalString` whenever the model
wants "let the user paste a polynomial" or "load a saved object as
code" without knowing the safer patterns (a dedicated parser, a
fixed-grammar dispatch table, or `Read`-from-file with a pre-vetted
path).

## What it flags

| Construct                                       | Why                          |
| ----------------------------------------------- | ---------------------------- |
| `EvalString( ... )`                             | Primary eval sink            |
| `ReadAsFunction( InputTextString( ... ) )`      | Read-string variant          |

Matches anchor on the symbol not preceded by an identifier
character, followed by `(`. Identifiers that merely contain
`EvalString` (`MyEvalStringHelper`, `EvalStrings`, `xEvalString`)
do not match.

## What it ignores

- Mentions inside `#` line comments.
- Mentions inside `"..."` strings and `'...'` character literals.
- Identifiers that merely contain the substring (see above).
- Lines marked with the suppression comment `# eval-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.g`, `*.gap`, `*.gi`, `*.gd`.

## Verified output

```
$ python3 detect.py examples/bad/
examples/bad/01_basic.g:3:1: gap-evalstring — EvalString(src);
examples/bad/02_function.g:3:12: gap-evalstring — return EvalString(expr);
examples/bad/03_concat.g:5:12: gap-evalstring — return EvalString(body);
examples/bad/04_readasfunction.g:4:10: gap-readasfunction-inputtextstring — f := ReadAsFunction(InputTextString(src));
examples/bad/05_loop.g:5:9: gap-evalstring — EvalString(line);
examples/bad/06_both_on_one_line.g:2:45: gap-readasfunction-inputtextstring — Twice := function(s) ...
examples/bad/06_both_on_one_line.g:2:30: gap-evalstring — Twice := function(s) ...
# 7 finding(s)

$ python3 detect.py examples/good/
# 0 finding(s)
```

The `examples/good/` files correctly produce zero findings,
including the doc strings that mention the sinks inside literals,
the lookalike identifiers (`MyEvalStringHelper`, `EvalStrings`,
`xEvalString`, `NotReadAsFunction`), the comment mentions, and
the suppressed `# eval-ok` line.

## Layout

```
detect.py                    # the scanner
examples/bad/*.g             # six intentional violations
examples/good/*.g            # four files with zero violations
```

# llm-output-scheme-eval-detector

Pure-stdlib python3 single-pass scanner that flags the
`(eval <string-derived-form>)` anti-idiom in Scheme source files
(R5RS / R6RS / R7RS / Racket / Guile / Chicken).

## What it detects

Scheme has a small but well-known anti-idiom for "build code as a
string and run it":

```scheme
(eval (read (open-input-string s))
      (interaction-environment))
```

This is the Scheme equivalent of Python's `exec(s)` or shell
`eval $cmd`. It silently bypasses the macro hygiene the language is
famous for, defeats `raco check-syntax` / Geiser-style static
analysis, breaks separate compilation, and — when any fragment of
the string flows from user input, an S-expression file written by
some other tool, an HTTP body, or a database column — turns into
arbitrary-code execution in the host Scheme runtime (with full FFI
reach in many implementations).

LLM-emitted Scheme code reaches for this pattern to dynamically
construct definitions, build expressions in a loop, or "let the user
type a snippet and run it". In every such case there is a safer,
more idiomatic alternative:

| Anti-idiom                       | Idiomatic Scheme                              |
| -------------------------------- | --------------------------------------------- |
| dynamic "variable name"          | a hash-table keyed by symbol/string           |
| dynamic expression               | `define-syntax` / `syntax-rules` macro        |
| parsing untrusted data           | `read` into a *datum*, pattern-match it       |
| compile-time codegen             | a hygienic macro (compile-time, not runtime)  |

The detector flags:

* `(eval (read (open-input-string ...)) ...)`         — R5/R7RS
* `(eval (read (open-string-input-port ...)) ...)`    — R6RS
* `(eval (read (call-with-input-string ...)) ...)`
* `(eval (with-input-from-string ... read) ...)`
* `(eval (read-from-string ...) ...)`                 — SRFI-30-ish
* `(eval (string->expression ...) ...)`
* `(eval (string->expr ...) ...)`

All shapes detected across multi-line spellings.

## What gets scanned

* Files with extension `.scm`, `.ss`, `.sld`, `.sps`, `.rkt`
  (matched case-insensitively).
* Directories are recursed.

## False-positive notes

* `(eval form env)` where `form` is a quoted/quasiquoted s-expression
  literal is **not** flagged — that's normal metaprogramming.
* `(read port)` *not* immediately consumed by `eval` is **not**
  flagged — the result is a datum, harmless on its own.
* `(load "file.scm")` is **not** flagged — that loads from a file
  path (a separate concern).
* Mentions inside `;` line comments or `"..."` strings are masked
  out before scanning.
* `#| ... |#` block comments are **not** specifically masked — they
  are rare in real Scheme code; on the off chance one wraps a
  matching pattern, silence with `; eval-string-ok`.
* Trailing `; eval-string-ok` comment on the same line suppresses
  that finding — use sparingly, e.g. for a unit-test helper that
  round-trips an internal sexpr.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

`<kind>` is one of `eval-read-string-port`,
`eval-with-input-from-string`, `eval-read-from-string`.

## Smoke test (verified)

```
$ python3 detect.py examples/bad.scm
examples/bad.scm:5:3: eval-read-string-port — (eval (read (open-input-string s))
examples/bad.scm:10:3: eval-read-string-port — (eval (read (open-string-input-port s))
examples/bad.scm:15:3: eval-with-input-from-string — (eval (with-input-from-string s read)
examples/bad.scm:20:3: eval-read-string-port — (eval (read (call-with-input-string s)) (interaction-environment)))
examples/bad.scm:24:3: eval-read-from-string — (eval (read-from-string s) (interaction-environment)))
examples/bad.scm:28:3: eval-read-from-string — (eval (string->expression s) (interaction-environment)))
examples/bad.scm:31:1: eval-read-string-port — (eval
# 7 finding(s)

$ python3 detect.py examples/good.scm
# 0 finding(s)
```

bad: **7** findings (covers R5RS `open-input-string`, R6RS
`open-string-input-port`, `with-input-from-string`,
`call-with-input-string`, `read-from-string`, `string->expression`,
and a multi-line spelling). good: **0** findings (covers hash-table
alternative, parse-as-data pattern, quoted/quasiquoted `eval`,
`syntax-rules` macro alternative, comment mention, string literal
mention, bare `read` without `eval`, and `; eval-string-ok`
suppression).

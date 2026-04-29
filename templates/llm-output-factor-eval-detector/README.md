# llm-output-factor-eval-detector

Detect runtime-string code-execution sinks in Factor source.

## Why

Factor is a concatenative stack language with first-class quotations.
The normal way to invoke a quotation (`call`) is safe -- the
quotation is a literal value typed by the compiler. The unsafe path
is when a *string* is parsed and executed at runtime via the
`eval` vocabulary:

* `"..." eval( -- )`         -- parse-and-call a string quotation
* `"..." (eval)`             -- lower-level equivalent
* `"..." parse-fresh call`   -- read a Factor source string then call
* `"..." parse-string call`  -- same threat model
* `"..." run-file`           -- if the path is built from input

LLM-generated REPL helpers and "build me a snippet on the fly"
recipes routinely concatenate user input into one of these strings.
Once the string is `eval`'d the attacker has full Factor (and via
`io.launcher:run-process`, full shell) access.

## What this flags

After blanking `! ...EOL` line comments, `#! ...EOL` shebang-style
comments, `( ... )` stack-effect comments, and the contents of
`"..."` string literals, the scanner looks for:

| Pattern                              | Kind                       |
| ------------------------------------ | -------------------------- |
| `eval(` (with stack effect)          | `factor-eval`              |
| `(eval)`                             | `factor-eval-private`      |
| `parse-fresh` followed by `call`     | `factor-parse-fresh-call`  |
| `parse-string` followed by `call`    | `factor-parse-string-call` |
| `run-file`                           | `factor-run-file`          |

A finding is upgraded to `-dynamic` when the *same line*, after
string-blanking, still contains a word reference (any non-quote
non-space token) preceding the sink -- i.e. the value being
evaluated did not arrive as a single bare string literal.

`call(` with a literal stack effect on a quotation is **not** flagged:
that is the safe, type-checked dispatch and is the whole point of
the language.

## Suppression

Append `! factor-eval-ok` on the same line.

## Fixtures

* `examples/bad/` -- 6 files, each demonstrates one sink kind
  (`eval(`, `(eval)`, `parse-fresh call`, `parse-string call`,
  `run-file`, dynamic-eval-of-concatenation).
* `examples/good/` -- 4 files: pure `call(` dispatch, quoted-only
  string that never reaches `eval`, suppressed line, and
  `eval` mention inside a `! comment` only.

## Usage

    python3 detector.py <file_or_dir> [...]

Recurses into directories looking for `*.factor`. Exit 1 if
findings, 0 otherwise. python3 stdlib only.

## Exit codes

* `0` -- no findings
* `1` -- one or more findings
* `2` -- usage error

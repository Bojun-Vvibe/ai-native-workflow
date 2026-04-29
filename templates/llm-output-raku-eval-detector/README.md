# llm-output-raku-eval-detector

Pure-stdlib python3 single-pass scanner that flags string-EVAL
anti-idioms in Raku (Perl 6) source files.

## What it detects

Raku ships an `EVAL` routine and a `MONKEY-SEE-NO-EVAL` pragma that
together let any program turn a runtime string into executable Raku
code:

```raku
use MONKEY-SEE-NO-EVAL;
EVAL $user-input;
```

This is the Raku spelling of Python `exec(s)` or shell `eval $cmd`.
The MONKEY pragma exists *precisely* because the language designers
want every such call to be conspicuous — but LLM-emitted code is
happy to write the pragma at the top of the file and then forget
why it was conspicuous.

`EVAL` also has language-tagged forms (`:lang<Perl5>`,
`:lang<Raku>`), a method-call form (`$expr.EVAL`), a file form
(`EVALFILE`), and reflective spellings via `$*W.compile($s)`,
`$*REPL.eval($s)`, or `Compiler.new.compile($s)`. Any of these,
fed user-controlled or otherwise untrusted text, is arbitrary-code
execution inside the Raku runtime — full IO, full shell, full FFI
via `NativeCall`.

The detector flags:

| Kind                     | Pattern                                          |
| ------------------------ | ------------------------------------------------ |
| `monkey-pragma`          | `use MONKEY-SEE-NO-EVAL` / `use MONKEY`          |
| `eval-call`              | `EVAL $x` / `EVAL(...)` / `EVAL "..."`           |
| `dot-eval`               | `$expr.EVAL`                                     |
| `evalfile`               | `EVALFILE` / `evalfile` (path-EVAL)              |
| `compile-string`         | `$*W.compile(...)`, `$*REPL.eval(...)`, `Compiler.new.compile(...)` |
| `lowercase-eval-string`  | Perl-5-style `eval $x` / `eval "..."` / `eval(`  |

## What gets scanned

* Files with extension `.raku`, `.rakumod`, `.rakudoc`, `.rakutest`,
  `.p6`, `.pm6`, `.pl6`, `.t6` (matched case-insensitively).
* Directories are recursed.

## False-positive notes

* Block-form `eval { ... }` is **not** flagged — that's exception
  trapping, not string-EVAL. Only `eval` followed by a value
  expression triggers `lowercase-eval-string`.
* Mentions inside `# ...` line comments, `=begin pod ... =end pod`
  blocks, and string literals (`"..."`, `'...'`, `q[...]`, `Q{...}`,
  `q(...)`, `Q<...>`) are masked out before scanning.
* Identifiers that merely *contain* the substring `eval`
  (e.g. `evaluator-stats`, `$eval-count`) are not matched — the
  detector requires word boundaries and a value-position prefix.
* `:EVAL` adverb keys are not matched (the regex excludes a leading
  `:`).
* Trailing `# eval-string-ok` comment on the same line suppresses
  that finding — use sparingly, e.g. for a unit-test helper that
  round-trips a known-safe internal blob.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified locally)

```
$ python3 detect.py examples/bad.raku
examples/bad.raku:3:1: monkey-pragma — use MONKEY-SEE-NO-EVAL;                       # bad-1: gating pragma
examples/bad.raku:6:5: eval-call — EVAL $s;                                   # bad-2: bareword EVAL
examples/bad.raku:10:5: eval-call — EVAL($s);                                  # bad-3: call form
examples/bad.raku:14:5: eval-call — EVAL $s, :lang<Perl5>;                     # bad-4: cross-lang EVAL
examples/bad.raku:18:10: dot-eval — $expr.EVAL;                                # bad-5: method form
examples/bad.raku:22:5: evalfile — EVALFILE $path;                            # bad-6: file EVAL
examples/bad.raku:26:5: compile-string — $*W.compile($s);                           # bad-7: reflective compile
examples/bad.raku:30:5: compile-string — $*REPL.eval($s);                           # bad-8: REPL.eval
examples/bad.raku:30:12: lowercase-eval-string — $*REPL.eval($s);                           # bad-8: REPL.eval
examples/bad.raku:34:5: lowercase-eval-string — eval "$s";                                  # bad-9: lowercase eval-string
examples/bad.raku:38:1: monkey-pragma — use MONKEY;                                    # bad-10: umbrella pragma
# 11 finding(s)

$ python3 detect.py examples/good.raku
# 0 finding(s)
```

bad: **11** findings across **10** distinct anti-patterns (one line
double-flags `$*REPL.eval(...)` as both `compile-string` and
`lowercase-eval-string`, which is intentional — both concerns
apply). good: **0** findings (covers `try { CATCH }` block-form
exception trap, hash-of-code-refs dispatch, EVAL mentions inside
all four kinds of string literal, EVAL mention in a `#` comment,
EVAL mention inside a `=begin pod ... =end pod` block, the
`# eval-string-ok` suppression for a fixture-only helper, and
identifiers that merely contain the substring `eval`).

# llm-output-fennel-eval-detector

Single-pass detector for **Fennel `(eval ...)`, `(eval-compiler ...)`,
and `(fennel.eval ...)`** runtime code-evaluation sinks.

## Why this exists

Fennel is a Lisp that compiles to Lua. It exposes a small set of
forms / library calls that compile a Fennel form supplied as data
and run it inside the host Lua VM:

```fennel
(eval form)                     ; evaluate a Fennel form at runtime
(eval-compiler ...)             ; run code in the compiler scope
(fennel.eval src options)       ; library entry point, takes a string
```

Whenever the argument is anything other than a manifest, audited
literal, the program is loading code chosen at runtime from data
that may be attacker-controllable: a config file, a network
response, a REPL prompt, a slot in a saved game file. Because
Fennel compiles to Lua and the result executes with the full Lua
standard library available, a string-eval sink is equivalent to a
Lua `loadstring`.

LLM-emitted Fennel code reaches for `eval` whenever the model wants
"a tiny config DSL" or "let the user supply a hook" without knowing
the safer patterns (a small interpreter over a fixed grammar, a
data-only config language, or the Fennel sandbox documented in the
official "Fennel for Lua programmers" reference).

## What it flags

| Construct                     | Why                                       |
| ----------------------------- | ----------------------------------------- |
| `(eval form)`                 | Primary eval sink                         |
| `(eval-compiler ...)`         | Compiler-scope variant                    |
| `(fennel.eval s)`             | Library entry point, string variant       |
| `(fennel.eval-string s)`      | Older string variant                      |

The match anchors on `(`, optional whitespace, then the symbol
followed by whitespace or `)`, so identifiers that merely contain
`eval` (`evaluate-score`, `re-eval`, `evaluator`) do not match.

## What it ignores

- Mentions inside `;` line comments.
- Mentions inside `"..."` string literals (Fennel uses Lua's string
  escape rules).
- Symbols whose names merely contain `eval` (see above).
- Lines marked with the suppression comment `; eval-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.fnl`.

## Verified output

```
$ python3 detect.py examples/
examples/bad/01_eval_form.fnl:3:1: fennel-eval — (eval form)
examples/bad/02_eval_compiler.fnl:2:1: fennel-eval-compiler — (eval-compiler (set _G.x 1))
examples/bad/03_fennel_eval.fnl:3:1: fennel-eval-string — (fennel.eval src)
examples/bad/04_eval_string.fnl:3:1: fennel-eval-string — (fennel.eval-string src)
examples/bad/05_loop_eval.fnl:4:5: fennel-eval — (eval f))
examples/bad/06_let_eval.fnl:3:5: fennel-eval — (eval form))
# 6 finding(s)
```

The `examples/good/` files correctly produce zero findings, including
the doc strings that mention `(eval ...)` inside literals, the
lookalike symbol names like `evaluate-score`, and the suppressed
`; eval-ok` line.

## Layout

```
detect.py                    # the scanner
examples/bad/*.fnl           # six intentional violations
examples/good/*.fnl          # four files with zero violations
```

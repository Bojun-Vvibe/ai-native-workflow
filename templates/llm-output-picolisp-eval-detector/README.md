# llm-output-picolisp-eval-detector

Single-pass detector for **PicoLisp `(eval ...)`, `(run ...)`,
and `(load ...)`** runtime code-load sinks.

## Why this exists

PicoLisp exposes a small set of built-ins that take Lisp data and
execute it as code. Whenever the argument is anything other than a
manifest, audited literal, the program is loading code chosen at
runtime from data that may be attacker-controllable (config,
network, REPL prompt, HTTP body, query string).

LLM-generated PicoLisp code reaches for `eval` / `run` / `load`
whenever the model wants "a tiny config DSL" or "let the user
supply a hook" without knowing the safer patterns (a small
interpreter over a fixed grammar, or a restricted env).

## What it flags

| Construct                     | Why                                       |
| ----------------------------- | ----------------------------------------- |
| `(eval form)`                 | Primary eval sink, even with literal arg  |
| `(eval (str s))`              | Classic data-to-code pipeline             |
| `(run prg)`                   | Executes a body of forms supplied as data |
| `(load path)`                 | Reads + evaluates an entire file          |

## What it ignores

- Mentions inside `# line` and `#{ ... }#` block comments.
- Mentions inside `"..."` string literals (PicoLisp `^` and
  backslash escapes both honored).
- Symbols whose names merely contain `eval`, `run`, or `load`
  (e.g. `evaluate-score`, `runner-state`, `loaded?`) — they don't
  match because the regex anchors on `(eval`, `(run`, or `(load`
  followed by whitespace or `)`.
- Lines marked with the suppression comment `# eval-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.l` and `*.lisp`.

## Verified output

```
$ python3 detect.py examples/bad/*
examples/bad/01_eval_str.l:3:4: picolisp-eval — (eval (str Input)) )
examples/bad/02_literal_eval.l:2:1: picolisp-eval — (eval '(+ 1 2 3))
examples/bad/03_load_user_path.l:3:4: picolisp-load — (load (pack "plugins/" Name ".l")) )
examples/bad/04_run_hooks.l:3:4: picolisp-run — (run Hooks) )
examples/bad/05_nested_let.l:4:15: picolisp-eval — (setq R (eval Form))
examples/bad/06_dynamic_load.l:3:4: picolisp-load — (load Mod)
# 6 finding(s)

$ python3 detect.py examples/good/*
# 0 finding(s)
```

The `examples/good/` files correctly produce zero findings, including
the doc string that mentions `(eval expr)` inside a literal, the
comment block, the lookalike symbols `evaluate-score` / `runner-state`
/ `loaded?`, and the suppressed `# eval-ok` line.

## Layout

```
detect.py                    # the scanner
examples/bad/*.l             # six intentional violations
examples/good/*.l            # four files with zero violations
```

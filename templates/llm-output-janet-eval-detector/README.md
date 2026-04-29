# llm-output-janet-eval-detector

Single-pass detector for **Janet `(eval ...)`, `(eval-string ...)`,
and `(dofile ...)`** runtime code-load sinks.

## Why this exists

Janet exposes a small set of functions that compile and run a Janet
form supplied as data. Whenever the argument is not a manifest,
audited literal, the program is loading code chosen from data that
may be attacker-controllable (config, network, REPL prompt, HTTP
body).

LLM-generated Janet code frequently reaches for `eval` when it wants
"a tiny config DSL" or "let the user supply a hook" without knowing
the safer patterns (a small interpreter over a fixed grammar, or a
PEG / spork sandbox).

## What it flags

| Construct                  | Why                                       |
| -------------------------- | ----------------------------------------- |
| `(eval form)`              | Primary eval sink, even with literal arg  |
| `(eval (parse src))`       | The classic data-to-code pipeline         |
| `(eval-string s)`          | String variant                            |
| `(dofile path)`            | Loads and runs another Janet source file  |

## What it ignores

- Mentions inside `# line` comments.
- Mentions inside `"..."` and `` `long-string` `` literals.
- Symbols whose names merely contain `eval` (e.g. `evaluate-score`,
  `re-evaluate`, `evaluator-name`) — they don't match because the
  regex anchors on `(eval`, `(eval-string`, or `(dofile` followed by
  whitespace or `)`.
- Lines marked with the suppression comment `# eval-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.janet` and `*.jdn`.

## Verified output

```
$ python3 detect.py examples/
examples/bad/01_eval_parse.janet:3:3: janet-eval — (eval (parse src)))
examples/bad/02_literal_eval.janet:2:1: janet-eval — (eval '(+ 1 2 3))
examples/bad/03_eval_string.janet:3:3: janet-eval-string — (eval-string s))
examples/bad/04_dofile.janet:3:3: janet-dofile — (dofile (string "plugins/" name ".janet")))
examples/bad/05_callback_eval.janet:5:3: janet-eval — (eval form))
examples/bad/06_nested_let.janet:4:5: janet-eval-string — (eval-string src)))
# 6 finding(s)
```

The `examples/good/` files correctly produce zero findings, including
the API-doc strings that mention `(eval ...)` inside literals, the
lookalike symbol names like `evaluate-score`, and the suppressed
`# eval-ok` line.

## Layout

```
detect.py                    # the scanner
examples/bad/*.janet         # six intentional violations
examples/good/*.janet        # four files with zero violations
```

# llm-output-elixir-code-eval-string-detector

## Purpose

Detect Elixir calls into the `Code` module that take a binary (or
quoted AST) and execute it inside the running BEAM node.

The flagged functions:

| Function | What it does |
| --- | --- |
| `Code.eval_string/1,2,3` | Parse a string as Elixir source and run it |
| `Code.eval_quoted/1,2,3` | Run a previously-built AST |
| `Code.eval_file/1,2`     | Read a file and run it |
| `Code.compile_string/1,2` | Compile a string into modules and load them |
| `Code.compile_quoted/1,2` | Compile an AST into modules and load them |
| `Code.compile_file/1,2`   | Compile a file into modules and load them |
| `Code.require_file/1,2`   | Read + compile + load a file |

These are the Elixir analogues of `eval()` on a string. If any portion
of the input comes from user input, network I/O, a database, or an LLM
prompt, calling them is a textbook RCE vector — anyone who controls
the input runs arbitrary BEAM code with the caller's permissions.

## Why LLM-emitted Elixir trips this

* Models translate Python `eval(expr)` literally into
  `Code.eval_string(expr)` instead of using pattern matching.
* Models implement "dynamic dispatch" via
  `Code.eval_string("MyMod." <> name <> "()")` instead of `apply/3`
  with an allowlist.
* Models implement "config loaders" via `Code.eval_file` instead of
  using `Config`, `Jason`, or `Toml`.

## When to use

- Reviewing LLM-generated `*.ex` / `*.exs` snippets before merging.
- CI lint over agent-authored Elixir.
- Pre-commit lint over a sample / examples directory.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it skips

- Calls inside `# ...` line comments.
- Calls inside single- / double-quoted string literals.
- Calls inside `"""` / `'''` heredoc bodies.
- `Code.string_to_quoted` (parses but does not execute — safe).
- Bare `eval_string(...)` without the `Code.` prefix (would be ambiguous
  with user-defined functions).

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — four Elixir files that MUST trigger.
- `good/` — two Elixir files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Smoke test (real output)

```
$ ./smoke.sh
bad_hits=6
good_hits=0
OK: bad=6 good=0

$ python3 detect.py bad/
bad/01_eval_string.ex:4:26: code-eval-string — {result, _binding} = Code.eval_string(input)
bad/02_dynamic_call.ex:5:18: code-eval-string — {value, _} = Code.eval_string(src)
bad/03_eval_file.ex:4:5: code-eval-file — Code.eval_file(path)
bad/03_eval_file.ex:8:5: code-compile-file — Code.compile_file(path)
bad/04_compile_string.exs:5:15: code-eval-quoted — {v, _b} = Code.eval_quoted(quoted)
bad/04_compile_string.exs:10:5: code-compile-string — Code.compile_string(src)
# 6 finding(s)

$ python3 detect.py good/
# 0 finding(s)
```

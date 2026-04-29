# llm-output-erlang-eval-detector

Pure-stdlib python3 single-pass scanner that flags string-eval and
runtime-compile anti-idioms in Erlang source files.

## What it detects

Erlang has no single `eval(String)` builtin the way Python does, but
the standard library ships several paths that together amount to
"compile and run an arbitrary string at runtime":

```erlang
{ok, Tokens, _} = erl_scan:string(Src),
{ok, Forms}     = erl_parse:parse_exprs(Tokens),
{value, V, _}   = erl_eval:exprs(Forms, []).
```

…or the `compile:forms/1` + `code:load_binary/3` path that turns a
runtime-built AST into a loaded module, plus the popular
`dynamic_compile` contrib that bundles all of the above behind one
call. Any of these, fed user-controlled or otherwise untrusted text,
is arbitrary-code execution inside the BEAM VM — full IO, full ports,
full NIF loading.

The detector flags:

| Kind                   | Pattern                                                         |
| ---------------------- | --------------------------------------------------------------- |
| `erl-eval`             | `erl_eval:exprs(...)`, `erl_eval:expr(...)`, `erl_eval:expr_list(...)` |
| `erl-scan-string`      | `erl_scan:string(...)`                                          |
| `erl-parse`            | `erl_parse:parse_exprs(...)` / `parse_form(...)` / `parse_term(...)` |
| `compile-forms`        | `compile:forms(...)` (runtime compile)                          |
| `code-load-binary`     | `code:load_binary(...)` (runtime load)                          |
| `dynamic-compile`      | `dynamic_compile:from_string(...)` / `load_from_string(...)`    |
| `list-to-atom-apply`   | `list_to_atom(...)` / `binary_to_atom(...)` on a line that also contains a `:` (apply heuristic) |

## What gets scanned

* Files with extension `.erl`, `.hrl`, `.escript`.
* Directories are recursed.

## False-positive notes

* `apply/3` with literal atoms is **not** flagged — that is normal
  dispatch.
* `list_to_atom` on its own line, with no `:` apply, is treated as
  a pure conversion and is **not** flagged.
* Mentions inside `% ...` line comments and string literals
  (`"..."`) are masked out before scanning.
* Single-quoted atoms (`'...'`) are deliberately *not* masked, so
  `'erl_eval':exprs(...)` still flags.

## Suppression

Trailing `% eval-string-ok` (or `%% eval-string-ok`) comment on the
same line suppresses that finding. Use sparingly and never on
user-tainted input.

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
$ python3 detect.py examples/bad.erl
examples/bad.erl:6:23: erl-scan-string — {ok, Tokens, _} = erl_scan:string(Src), ...
examples/bad.erl:7:23: erl-parse — {ok, Forms}     = erl_parse:parse_exprs(Tokens), ...
examples/bad.erl:8:23: erl-eval — {value, V, _}   = erl_eval:exprs(Forms, []), ...
examples/bad.erl:9:9:  erl-eval — _ = erl_eval:expr(hd(Forms), []), ...
examples/bad.erl:10:9: erl-eval — _ = erl_eval:expr_list(Forms, [], []), ...
examples/bad.erl:11:9: erl-parse — _ = erl_parse:parse_term(Tokens), ...
examples/bad.erl:12:21: compile-forms — {ok, _M, Bin} = compile:forms(Forms), ...
examples/bad.erl:13:21: code-load-binary — {module, M2}  = code:load_binary(my_mod, "my_mod.erl", Bin), ...
examples/bad.erl:14:9: dynamic-compile — _ = dynamic_compile:from_string(Src), ...
examples/bad.erl:15:9: dynamic-compile — _ = dynamic_compile:load_from_string(Src), ...
# 10 finding(s)

$ python3 detect.py examples/good.erl
# 0 finding(s)
```

bad: **10** findings across the seven detector kinds. good: **0**
findings (covers `apply/3` with literal atoms, `list_to_atom` used
purely as a conversion with no apply on the same line, the
dangerous identifiers mentioned only inside a `%`-style comment,
the same identifiers mentioned only inside a `"..."` string
literal, and one explicit `%% eval-string-ok` suppression on a
fixture-only path).

# llm-output-julia-eval-detector

Pure-stdlib python3 single-pass scanner that flags Julia
dynamic-code execution sinks (`eval`, `@eval`, `Meta.parse`,
`include_string`) in Julia source files.

## What it detects

In Julia, `eval(ex)` evaluates an `Expr` in the current module, and
`Meta.parse(s)` turns an arbitrary source string into an `Expr`.
`eval(Meta.parse(user_input))` — or any `eval` on a value built
from runtime data — is a code-injection sink with the same blast
radius as `system($USER_INPUT)`. `@eval` (the macro form) and
`include_string` have the same effect.

LLM-emitted Julia reaches for `eval` to "build a function from a
template string" or "compute a symbol the user named". Almost
always wrong. Safe alternatives:

* a `Dict{String, Function}` dispatch table,
* multiple dispatch / generated functions for the type-driven case,
* `getfield(Module, Symbol(name))` *only* against a hard-coded
  whitelist of allowed symbols.

The detector flags each sink call independently; nested forms like
`eval(Meta.parse(s))` produce two findings on the same line.
Suppress an audited line with a trailing `# eval-ok` comment.

## What gets scanned

* Files with extension `.jl`.
* Files whose first line is a shebang containing `julia`.
* Directories are recursed.

## What gets flagged

* `eval(...)` — module-level / imported.
* `Core.eval(...)` and `Base.eval(...)` — fully-qualified.
* `@eval ...` — macro form.
* `Meta.parse(...)` — string-to-Expr (almost always paired with eval).
* `include_string(...)` — direct string execution.

Out of scope (deliberately): `include("file.jl")` reads a path, not
a runtime string; a separate detector can target it.

## False-positive notes

* Any sink token inside a `#` line comment, a `#= ... =#` block
  comment that fits on one line, a `"..."` string literal, or a
  single-line `"""..."""` triple string is masked out before scanning.
* `# eval-ok` on a line suppresses that line entirely.
* Multi-line block comments and multi-line triple strings are not
  tracked across lines; in practice LLM-emitted Julia almost never
  triggers this.
* The detector does not try to prove the argument is a constant
  `Expr` — even constant-`Expr` `eval` is a smell worth a human
  glance, so `eval(:(2 + 2))` is flagged. Add `# eval-ok` if
  intentional.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: julia-eval — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad.jl
examples/bad.jl:7:10: julia-eval — result = eval(Meta.parse(user_input))
examples/bad.jl:7:15: julia-eval — result = eval(Meta.parse(user_input))
examples/bad.jl:11:1: julia-eval — include_string(Main, "x_runtime = 42")
examples/bad.jl:16:1: julia-eval — @eval $(fname)(x) = x * 2
examples/bad.jl:19:1: julia-eval — Core.eval(Main, Meta.parse("y_runtime = 7"))   # TWO findings on this line
examples/bad.jl:19:17: julia-eval — Core.eval(Main, Meta.parse("y_runtime = 7"))   # TWO findings on this line
examples/bad.jl:23:1: julia-eval — Base.eval(Main, :(z_runtime = 99))
examples/bad.jl:27:8: julia-eval — expr = Meta.parse("3 + 4")
examples/bad.jl:28:9: julia-eval — println(eval(expr))   # TWO findings: Meta.parse line above + eval here
# 9 finding(s)

$ python3 detect.py examples/good.jl
# 0 finding(s)
```

bad: **9** findings, good: **0** findings.

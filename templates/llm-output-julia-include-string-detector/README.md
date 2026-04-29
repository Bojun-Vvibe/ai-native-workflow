# llm-output-julia-include-string-detector

Static detector for **string-as-code** sinks in [Julia](https://julialang.org/) (`.jl`) files an LLM may emit when wiring up "let the user supply Julia code" or "fetch a script from the network and run it".

## Problem

Julia exposes several APIs that take a *string* and execute it as Julia code at runtime. They are functionally equivalent to `eval` for the purposes of remote-code-execution if the string ever reaches them from an untrusted source:

| Sink | What it does |
|------|--------------|
| `include_string(mod, str [, fname])` | Parses `str` as Julia source and evaluates it in `mod`. |
| `include(download(url))` / `include(HTTP.get(url).body)` | `include` accepts a stream/path; combined with a network read it becomes RCE-by-design. |
| `eval(Meta.parse(str))` / `Core.eval(m, Meta.parse(str))` | The classic two-step: turn a string into an AST, then evaluate it. |
| `eval(Meta.parseall(str))` | Multi-statement variant. |
| `Base.invokelatest(eval, Meta.parse(str))` | Same sink wrapped to dodge world-age errors. |

This detector is intentionally distinct from `llm-output-julia-eval-detector`, which targets `eval(...)` of a literal `Expr`. Evaluating a literal AST built at compile time is normal Julia metaprogramming; evaluating a *string* is not.

## What the detector flags

- `include-string` — `include_string(...)`
- `include-from-net` — `include(download(...))` / `include(HTTP.get(...).body)` / `include(read(...))`
- `meta-parse-eval` — `eval(... Meta.parse(...))` or `Core.eval(... Meta.parse(...))`
- `parseall-eval` — `eval(... Meta.parseall(...))`
- `invokelatest-eval` — `Base.invokelatest(eval, Meta.parse(...))`

## What it deliberately does NOT flag

- `eval(:(x = 1))` or `eval(expr)` where `expr` is a locally-built `Expr` — that's normal metaprogramming, not string-as-code.
- `include("path/to/file.jl")` with a literal path or `joinpath(...)` — fixed-path includes are how Julia projects load modules.
- Mentions of any sink name inside a `# ...` comment, a `#= ... =#` block comment, a `"..."` string, or a `"""..."""` triple-quoted docstring — all four are masked before regex matching.

## How it works

Single pass, python3 stdlib only (`detector.py`). The `mask()` function walks the source character by character, tracking four mutually-exclusive states (block comment with depth, triple-quoted string, regular string, char literal) and replacing their contents with spaces while preserving newlines so reported line numbers stay accurate. After masking, five compiled regexes are run per line; first match wins per line.

## Usage

```sh
python3 detector.py path/to/project/ src/loader.jl
```

Exit code `1` if any finding is emitted, `0` otherwise — drop straight into pre-commit / CI.

## Live smoke test

```
$ bash verify.sh
== bad/ ==
bad/01_include_string_basic.jl:5:12: include-string return include_string(@__MODULE__, snippet)
bad/02_include_from_net.jl:4:1: include-from-net include(download(url))
bad/03_meta_parse_eval.jl:8:12: meta-parse-eval quick(s) = eval(Meta.parse(s))
bad/04_parseall_eval.jl:5:17: parseall-eval return Core.eval(@__MODULE__, Meta.parseall(blob))
bad/05_invokelatest.jl:3:5: invokelatest-eval Base.invokelatest(eval, Meta.parse(src))
bad/06_docstring_obfuscated.jl:9:12: include-string return include_string(Main, snippet, "user.jl")
bad/07_after_triple_string.jl:10:1: include-string include_string(Main, read("payload.jl", String))
bad/08_after_block_comment.jl:7:1: include-from-net include(HTTP.get("https://example.invalid/mod.jl").body)
== good/ ==
-- summary --
bad-findings:  8  (expected: >= 8)
good-findings: 0 (expected: 0)
PASS
```

The `good/` corpus deliberately mentions every sink name inside line comments, block comments, regular string literals, and triple-quoted docstrings, to verify the masker.

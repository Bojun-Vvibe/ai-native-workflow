# llm-output-r-eval-parse-detector

Pure-stdlib python3 single-pass scanner that flags the
`eval(parse(text = ...))` anti-idiom (and its `str2lang` /
`str2expression` cousins) in R source files.

## What it detects

R has a well-known anti-idiom for "build code as a string and run it":

```r
eval(parse(text = paste0("model_", i, " <- lm(...)")))
```

This is the R equivalent of Python's `exec(s)` or shell `eval $cmd`.
It silently bypasses lexical scoping, defeats syntax checking, breaks
`R CMD check` static analysis, and — when any fragment of the string
flows from user input, a CSV cell, an HTTP parameter, or a database
column — turns into arbitrary-code execution.

LLM-emitted R code reaches for this pattern to dynamically construct
variable names, build formulas, or "loop and create N models". In
every such case there is a safer, more idiomatic alternative:

| Anti-idiom                               | Idiomatic R                                      |
| ---------------------------------------- | ------------------------------------------------ |
| dynamic variable name                    | use a `list()` / named vector / `env`            |
| dynamic formula                          | `as.formula(paste0(...))` then `lm(formula, data)` |
| dynamic column reference                 | `df[[name]]` or `dplyr::sym(name)`               |
| metaprogramming / code generation        | `bquote()` / `substitute()` / `rlang::expr()`    |

The detector flags:

* `eval(parse(text = ...))`   — including multi-line spelling
* `eval(parse(text=paste0(...)))`, `sprintf(...)`, etc.
* `evalq(parse(text = ...))`
* `base::eval(parse(text = ...))` — fully qualified
* `eval(str2lang(...))`         — same anti-idiom, different surface
* `eval(str2expression(...))`

## What gets scanned

* Files with extension `.R`, `.r`, `.Rmd`, `.rmd`, `.Rnw` (matched
  case-insensitively).
* Directories are recursed.

## False-positive notes

* `parse(file = "script.R")` followed by `eval(...)` is a legitimate
  "source another file" pattern and is NOT flagged — only `text=`
  triggers the detector.
* Mentions of `eval(parse(text = ...))` inside a `#` comment or
  inside a `"..."`/`'...'`/backtick string literal are masked out
  before scanning.
* `eval(some_quoted_expression)` without `parse()` (normal
  metaprogramming) is NOT flagged.
* Trailing `# eval-parse-ok` comment on the same line suppresses
  that finding — use sparingly, e.g. for an internal knitr/rmarkdown
  chunk-option parser whose input is fully internal.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

`<kind>` is one of `eval-parse-text`, `eval-str2lang`.

## Smoke test (verified)

```
$ python3 detect.py examples/bad.R
examples/bad.R:5:3: eval-parse-text — eval(parse(text = paste0("model_", i, " <- lm(y ~ x, data = df)")))
examples/bad.R:10:3: eval-parse-text — eval(parse(text = sprintf("summary(df$%s)", col)))
examples/bad.R:15:3: eval-parse-text — eval(parse(text = paste0("df$", name)))
examples/bad.R:19:1: eval-parse-text — base::eval(parse(text = "x <- 1 + 1"))
examples/bad.R:22:1: eval-parse-text — evalq(parse(text = "y <- 2"))
examples/bad.R:26:3: eval-str2lang — eval(str2lang(s))
examples/bad.R:31:3: eval-str2lang — eval(str2expression(s))
examples/bad.R:35:1: eval-parse-text — eval(
# 8 finding(s)

$ python3 detect.py examples/good.R
# 0 finding(s)
```

bad: **8** findings (covers single-line, multi-line, fully-qualified,
`evalq`, and `str2lang`/`str2expression` variants). good: **0** findings
(covers `parse(file=)`, `quote()`/`bquote()`, comment mention, string
literal mention, and `# eval-parse-ok` suppression).

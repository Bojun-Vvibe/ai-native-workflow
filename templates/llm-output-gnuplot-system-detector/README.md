# llm-output-gnuplot-system-detector

Static detector for **dynamic-shell sinks** in gnuplot script files (`.gp`, `.plt`, `.gnu`, `.gnuplot`) that an LLM may emit when wiring up "render the plot then convert to PNG", "load this user's color palette", or "embed today's hostname in the title".

## Problem

Gnuplot is a small DSL but ships with several runtime-shell escapes that turn a plotting script into a code-execution surface the moment any input is attacker-influenced:

| Sink | What it does |
|------|--------------|
| `system("cmd")` | runs `cmd` in a subshell, returns stdout |
| `` `cmd` `` (backticks, even inside `"..."` strings) | shell substitution; output spliced into the surrounding string |
| `set print "\|cmd"` | opens a shell pipe; everything `print` writes goes to `cmd`'s stdin |
| `load EXPR` | reads a file at runtime and executes it as gnuplot code (the `do FILE` of gnuplot) |
| `call EXPR` | same as `load`, with positional args |
| `eval(strexpr)` | evaluates a *string* as a gnuplot command - the textbook eval sink |

LLMs reach for `system(...)` and backticks the moment a prompt mentions "after the plot is saved, ...". `load` / `call` look harmless because their static form is the canonical "include another script" idiom; the dangerous form is when the path is a variable.

## What the detector flags

- `system-call`     - `system(...)` (any argument)
- `backtick-call`   - `` `...` `` anywhere on a non-comment line (gnuplot expands them inside double-quoted strings, so we deliberately match against the raw line)
- `set-print-pipe`  - `set print "|..."` or `set print '|...'`
- `load-dynamic`    - `load EXPR` where `EXPR` is not a single literal string
- `call-dynamic`    - `call EXPR` where `EXPR` is not a single literal string
- `eval-string`     - `eval(...)` (any argument)

## What it deliberately does NOT flag

- `system` / `eval` / `load` / `call` mentioned inside a `# ...` line comment.
- `system` / `eval` / `load` / `call` mentioned inside a `"..."` or `'...'` string body (the body is masked before regex matching).
- `load "static.gp"` / `call "lib/render.gp"` - bareword-static-string forms are the normal include idiom.
- `set print "results.log"` (no leading `|`).

## How it works

Single pass, python3 stdlib only (`detector.py`). The `mask()` function blanks gnuplot line comments (`# ...`) and the interiors of single- and double-quoted strings while preserving newlines so reported line numbers stay accurate. After masking, three top-level regexes (`system(...)`, `eval(...)`, `load|call <expr>`) fire; the `load|call` arm additionally inspects the argument and only reports when the argument is **not** a single literal string. The `set print "|..."` check runs against the raw line (with trailing comment stripped) because the `|` lives inside the string and would be masked away. The backtick check runs against the raw line for the same reason.

## Usage

```sh
python3 detector.py path/to/scripts/ render.gp
```

Exit code `1` if any finding is emitted, `0` otherwise - drop straight into pre-commit / CI.

## Live smoke test

```
$ bash verify.sh
== bad/ ==
bad/01_system_call.gp:6:1: system-call system("convert out.png out.pdf")
bad/02_backtick.gp:2:26: backtick-call title_str = "rendered on `hostname` at `date +%H:%M`"
bad/03_set_print_pipe.gp:4:1: set-print-pipe set print "|tee log-".tag.".txt"
bad/04_load_dynamic.gp:3:1: load-dynamic load plugin
bad/05_call_dynamic.gp:4:1: call-dynamic call base . name . ".gp" "arg1"
bad/06_eval_string.gp:3:1: eval-string eval(expr)
== good/ ==
-- summary --
bad-findings:  6  (expected: >= 6)
good-findings: 0 (expected: 0)
PASS
```

The `good/` corpus exercises every false-positive trap: comments-only mentions, string-body mentions, static literal `load` / `call`, and a static (non-pipe) `set print`.

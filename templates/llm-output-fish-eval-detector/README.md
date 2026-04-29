# llm-output-fish-eval-detector

Static detector for dynamic-code-execution sinks in [fish-shell](https://fishshell.com/) scripts that an LLM may emit when generating shell automation, dotfiles, or installer one-liners.

## Problem

Fish, like POSIX shells, has a small but lethal set of constructs that turn a string into executable code at runtime:

| Sink | Risk |
|------|------|
| `eval $var` | Re-parses arbitrary text as shell — full RCE if `$var` is attacker-influenced. |
| `eval (cmd)` | Same, but the source string comes from a command substitution (typically `curl`). The classic *curl-pipe-to-shell* pattern. |
| `... \| source` | Pipes arbitrary text into the fish parser. Equivalent to `eval` for whole-program payloads. |
| `source -` / `. -` | Reads code from stdin and executes it. |

LLMs generate these confidently when asked for "make this dynamic", "let the user supply the command", or "fetch the install script from the internet". The detector catches them before the script is shipped.

## What the detector flags

- `eval-with-cmdsub` — `eval (...)` form
- `eval-with-var` — `eval $foo`
- `eval-bare` — any other `eval <something>`
- `source-stdin` — `source -` or `. -`
- `pipe-to-source` — `... | source` / `... | .`

## What it deliberately does NOT flag

- `eval` appearing inside a string literal (`"... eval ..."`) or after a `#` comment — these are masked before regex matching.
- `source <real-file>` — sourcing a fixed path is normal fish usage.
- `switch ... case ...` dispatch — the safe alternative to `eval`.

## Implementation notes

Single pass, python3 stdlib only. The `mask()` function strips comment tails and string-literal interiors while preserving column count, so line/column reporting stays accurate and false positives from prose-in-strings disappear.

Note: fish does not support escaped quotes the same way bash does. `mask()` treats `\"` and `\'` conservatively as escaped, which slightly over-strips inside single-quoted strings (fish single-quotes are literal). This is safe for detection — it only widens the masked region, never narrows it.

## Usage

```sh
python3 detect.py path/to/scripts/ another.fish
```

Exit code `1` if any finding is emitted, `0` otherwise — drop into pre-commit / CI directly.

## Live smoke test

```
$ python3 detect.py examples/bad/ examples/good/
examples/bad/02_eval_cmdsub.fish:1: [eval-with-cmdsub] eval (curl -s https://example.invalid/setup.fish)
examples/bad/03_eval_in_function.fish:3: [eval-with-var] eval $cmd
examples/bad/06_eval_after_semicolon.fish:1: [eval-bare] set name $argv[1]; eval echo hello $name
examples/bad/04_pipe_to_source.fish:1: [pipe-to-source] curl -s https://example.invalid/init.fish | source
examples/bad/05_source_stdin.fish:1: [source-stdin] echo "set x 42" | source -
examples/bad/01_eval_var.fish:2: [eval-with-var] eval $user_input
-- 6 finding(s)
$ echo $?
1
```

All 6 `examples/bad/*.fish` files produce the expected finding; all 4 `examples/good/*.fish` files (including ones that mention the literal word `eval` inside strings and comments) report zero.

## Safe alternatives

| Instead of | Use |
|------------|-----|
| `eval $cmd` | `switch $cmd; case build; make; case test; make test; end` |
| `curl ... \| source` | Download to a versioned, hash-checked file then `source ./pinned.fish` |
| `eval (cmd)` | Capture into a variable, validate, then dispatch via `switch` |

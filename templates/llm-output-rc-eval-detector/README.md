# llm-output-rc-eval-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** Plan 9 `rc` shell `eval` and `.` (dot/source) constructs in
`*.rc` files and any file whose first line is an rc shebang
(`#!/usr/bin/rc`, `#!/bin/rc`, `#!/usr/local/plan9/bin/rc`, `#!/usr/bin/env rc`).

## Why this matters for LLM-generated rc

LLMs that have only seen bash get the syntax of `rc` slightly wrong
in ways that quietly become injection bugs. Two builtins are the
usual sinks:

1. `eval $cmd` — joins its arguments with spaces, then re-parses the
   result as fresh rc source. If `$cmd` came from `argv`, an env
   var, the contents of a file, or `` `{...} `` output, the caller
   controls the script.
2. `. $path` — rc's source builtin. A dynamic path lets the caller
   point the script at attacker-controlled rc source. Same blast
   radius as `eval`.

rc does NOT have `$(...)`. Command substitution is `` `{cmd} ``
(braces required for a multi-token command) or older bare
`` `cmd ``. Variables are `$var`, `$"var`, `$#var`. The detector
keys off `$` and backtick on the same line as `eval` / `.`.

## What this flags

| construct                                  | flagged?           |
| :----------------------------------------- | :----------------: |
| `eval $cmd`                                | yes                |
| `eval 'echo' $header`                      | yes                |
| `` eval `{git config --get alias.$x} ``    | yes                |
| `` eval `cat $f` ``                        | yes                |
| `eval $cmd` after `;`, `&`, `|`, `if`, `while` | yes            |
| `. $cfgfile`                               | yes (`rc-dot-dynamic`) |
| `. ./lib/'$thing'.rc` (literal)            | NO                 |
| `eval 'x = 1; y = 2'` (purely literal)     | NO                 |
| `eval 'fn helper { echo hi }'` (literal)   | NO                 |

## Suppression

Append `# eval-ok` to the line after manual review.

## Usage

```sh
python3 detect.py path/to/script.rc
python3 detect.py examples/bad examples/good
```

Exit code is `1` if any findings, `0` otherwise. Finding lines look
like:

```
examples/bad/01_basic.rc:3:1: rc-eval-dynamic — eval $cmd
```

## Worked example

```sh
./verify.sh
```

Asserts `examples/bad/` produces ≥7 findings and `examples/good/`
produces 0. Exits 0 on PASS.

## Known limits

* Heredoc bodies are not parsed; `eval` written inside a heredoc
  body would be flagged spuriously. rc heredocs are uncommon — if
  you hit this, suppress with `# eval-ok` on the heredoc-delimiter
  line.
* Multiline `eval { ... }` blocks where the dynamic argument is on
  a continuation line are not flagged. A safer detector would need
  full lexing; the single-line heuristic catches the overwhelming
  majority of LLM mistakes.
* `~ $path *.rc` (rc's pattern-match builtin) is intentionally not
  flagged — it is a comparison, not an exec.

## Why python3 stdlib only

Same constraints as the rest of the `llm-output-*-detector` family:
zero install footprint, runs anywhere a recent python is on PATH,
trivial to vendor into a CI step.

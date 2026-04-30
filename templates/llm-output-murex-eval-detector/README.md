# llm-output-murex-eval-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** invocations of the Murex `eval` builtin in `*.mx` /
`*.murex` files (and any file with a `#!.../murex` shebang).

## What it catches

Murex (https://murex.rocks) is a typed, content-aware POSIX-ish
shell aimed at DevOps. Its `eval` builtin takes a string of
murex source code and parses + executes it at runtime. As with
every shell-eval, the moment an argument string is built from a
`$var` parameter expansion or a `${cmd ...}` murex inline
subshell, an attacker who controls that value gains arbitrary
murex (and therefore arbitrary process) execution.

Murex string quoting:

- `'...'`     — literal single-quoted string, no expansion
- `(...)`     — literal parens-quoted string, no expansion
- `%(...)`    — literal percent-paren string, no expansion
- `"..."`     — interpolating double-quoted string, expands
                `$var` and `${command ...}`

Murex also has the `command` builtin and the `builtin` builtin
that can prefix any other builtin to bypass user-defined
functions of the same name. The scanner catches both
`command eval ...` and `builtin eval ...` prefix forms; LLMs
sometimes emit those as a "more portable" alternative without
realising they have the same exec hazard.

A purely literal `eval 'echo hello'`, `eval (echo hello)`, or
`eval %(echo hello)` is **not** flagged. Suppress an audited
line with a trailing `# eval-ok` comment.

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — eight `.mx` files, each demonstrating one
  dynamic `eval` shape that should fire (including the
  `command eval` and `builtin eval` prefix forms, and the
  `${cmd}` inline-subshell form).
- `examples/good/` — seven `.mx` files (literal single-quoted,
  literal parens-quoted, literal `%()`-quoted, comment-only
  mention, suppressed, look-alike identifiers, single-quoted
  body) that must **not** fire.
- `verify.sh` — runs `detect.py` against `examples/bad` and
  `examples/good`, asserts `bad >= 8`, `good == 0`, and exits 0
  on PASS / 1 on FAIL.

## Usage

```sh
python3 detect.py path/to/scripts/
```

Exit code 1 if any findings, 0 otherwise. Output is one
`file:line:col: murex-eval-dynamic — <line>` per finding plus a
trailing `# N finding(s)` summary.

## Verification

Actual output of `./verify.sh` on this template's fixtures:

```
$ ./verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

Sample finding lines emitted while scanning `examples/bad/`:

```
examples/bad/01_eval_var.mx:3:1: murex-eval-dynamic — eval $user
examples/bad/02_eval_dq.mx:3:1: murex-eval-dynamic — eval "echo hello $name"
examples/bad/03_eval_inline_subshell.mx:2:1: murex-eval-dynamic — eval "${cat /tmp/payload.mx}"
examples/bad/04_eval_after_semi.mx:2:9: murex-eval-dynamic — x = $1; eval $x
examples/bad/05_command_eval.mx:4:1: murex-eval-dynamic — command eval $arg
examples/bad/06_builtin_eval.mx:5:1: murex-eval-dynamic — builtin eval $arg
examples/bad/07_eval_in_block.mx:3:5: murex-eval-dynamic — eval "process $f"
examples/bad/08_eval_concat_dq.mx:5:1: murex-eval-dynamic — eval "$prefix $target"
# 8 finding(s)
```

`bad=8/good=0 PASS`.

## Limitations

- Heuristic, line-oriented. A multi-line `eval` continuation will
  only be evaluated against its first physical line.
- Does not statically prove that `$var` is attacker-controlled — it
  only flags the dynamic surface. Triage findings against the
  source of each variable; suppress with `# eval-ok` once audited.
- Recognizes `.mx`, `.murex` plus shebang sniffing; files invoked
  via an unconventional path won't be picked up in directory mode.
- The `command` / `builtin` prefixes are matched literally — other
  builtin-bypass tricks (aliases, `fexec`) are not yet recognised.
- Parens-quoted strings (`(...)`) overlap syntactically with
  murex's block-grouping parens used in things like
  `if (cond) { ... }`. The scrubber only treats a `(` as
  literal-string opening when preceded by whitespace; this can
  occasionally under-flag complex one-liners, never over-flag.

# llm-output-oil-eval-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** invocations of the Oil (oils-for-unix) `eval` builtin in
`*.osh`, `*.ysh`, `*.oil` files (and any file with a `#!.../osh`,
`#!.../ysh`, or `#!.../oil` shebang).

## What it catches

Oil — packaged today as `oils-for-unix`, with OSH (the
bash-compatible language) and YSH (the new language) — ships an
`eval` builtin. Like every other Bourne descendant, that builtin
concatenates its string arguments with spaces and re-parses them
as shell input: full word splitting, parameter expansion, command
substitution, redirection, the lot. When any argument is built
from a `$var` / `${var}`, a `$(cmd)` command substitution, or a
backtick `` `cmd` `` substitution, an attacker who controls that
value gains arbitrary shell execution.

Oil also exposes the YSH variant `eval (myblock)` which takes a
*block literal* — that form is structurally safe and is
**not** flagged. Likewise `eval $'literal C-string'` and
`eval r'raw literal'` are treated as literals because Oil's
`$'...'` only processes backslash escapes, never `$var` or
`$(...)`, and `r'...'` is fully raw.

The `command` builtin can prefix `eval` (`command eval ...`) to
bypass any user-defined function named `eval`. The scanner catches
that prefix form too; LLMs sometimes emit it as a "more portable"
alternative without realising it has the same exec hazard.

A purely literal `eval 'echo hello'` (single-quoted; no `$`,
`$(`, or `` ` ``) is **not** flagged. Suppress an audited line
with a trailing `# eval-ok` comment.

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — eight files, each demonstrating one dynamic
  `eval` shape that should fire (including the `command eval`
  prefix form).
- `examples/good/` — seven files (literal eval, comment-only
  mention, single-quoted, suppressed, look-alike identifiers,
  `$'...'` C-string + `r'...'` raw form, and YSH block-literal
  `eval (block)`) that must **not** fire.
- `verify.sh` — runs `detect.py` against `examples/bad` and
  `examples/good`, asserts `bad >= 8`, `good == 0`, and exits 0
  on PASS / 1 on FAIL.

## Usage

```sh
python3 detect.py path/to/scripts/
```

Exit code 1 if any findings, 0 otherwise. Output is one
`file:line:col: oil-eval-dynamic — <line>` per finding plus a
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
examples/bad/01_eval_var.osh:3:1: oil-eval-dynamic — eval $user
examples/bad/02_eval_dq.osh:3:1: oil-eval-dynamic — eval "echo hello $name"
examples/bad/03_eval_cmdsub.osh:2:1: oil-eval-dynamic — eval "$(cat /tmp/payload.osh)"
examples/bad/04_eval_backtick.osh:2:1: oil-eval-dynamic — eval `cat /tmp/payload.osh`
examples/bad/05_eval_after_semi.osh:2:9: oil-eval-dynamic — x="$1"; eval $x
examples/bad/06_command_eval.osh:4:1: oil-eval-dynamic — command eval $arg
examples/bad/07_eval_after_do.osh:3:3: oil-eval-dynamic — eval "process $f"
examples/bad/08_eval_brace_param.osh:3:1: oil-eval-dynamic — eval "echo \"the value of $key is ${!key}\""
# 8 finding(s)
```

`bad=8/good=0 PASS`.

## Limitations

- Heuristic, line-oriented. A multi-line `eval` continuation built
  with `\` line-continuation will only be evaluated against its
  first physical line.
- Does not statically prove that `$var` is attacker-controlled — it
  only flags the dynamic surface. Triage findings against the
  source of each variable; suppress with `# eval-ok` once audited.
- Recognizes `.osh`, `.ysh`, `.oil` plus shebang sniffing of the
  first line; files invoked via an unconventional path won't be
  picked up in directory mode. The `command` prefix is matched
  literally — other builtin-bypass tricks (`builtin eval`,
  aliasing) are not yet recognised.
- YSH block-form detection is intentionally conservative: any
  `eval` whose first non-space argument is `(` is treated as a
  block-literal call and skipped. A pathological line like
  `eval (echo $x)` would therefore be missed; in practice OSH
  parses that as a subshell-expression argument and the recommended
  form for dynamic shell-string eval remains the bare `eval $x`.

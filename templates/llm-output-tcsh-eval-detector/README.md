# llm-output-tcsh-eval-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** invocations of the tcsh / csh `eval` builtin in `*.tcsh`
and `*.csh` files (and any file with a `#!.../tcsh` or `#!.../csh`
shebang).

## What it catches

`eval string ...` re-parses its arguments through the full csh
parser — globbing, history substitution (`!`), command substitution
(`` ` ``), variable expansion (`$`), and execution. When any of
those arguments are built from a `$var`, a backtick command
substitution, or a history reference like `!$`, an attacker who
controls that value gains arbitrary tcsh execution. LLMs frequently
emit `eval $cmd` or ``eval `curl $url` `` for "run whatever the
caller passes in" snippets — exactly the shape this scanner exists
to catch.

A purely literal `eval 'echo hello'` (single-quoted, no `$`,
no `` ` ``, no `!`) is **not** flagged. Suppress an audited line
with a trailing `# eval-ok` comment.

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — eight `.tcsh` files, each demonstrating one
  dynamic `eval` shape that should fire.
- `examples/good/` — five `.tcsh` files (literal eval, comment-only
  mention, single-quoted, suppressed, and look-alike identifiers)
  that must **not** fire.
- `verify.sh` — runs `detect.py` against `examples/bad` and
  `examples/good`, asserts `bad >= 8`, `good == 0`, and exits 0
  on PASS / 1 on FAIL.

## Usage

```sh
python3 detect.py path/to/scripts/
```

Exit code 1 if any findings, 0 otherwise. Output is one
`file:line:col: tcsh-eval-dynamic — <line>` per finding plus a
trailing `# N finding(s)` summary.

## Example run

```
$ ./verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

`bad=8/good=0 PASS`.

## Limitations

- Heuristic, line-oriented. A multi-line `eval` continuation built
  with `\` line-continuation will only be evaluated against its
  first physical line (typical csh style emits eval on one line, so
  this is rarely an issue in practice).
- Does not statically prove that `$var` is attacker-controlled — it
  only flags the dynamic surface. Triage findings against the
  source of each variable; suppress with `# eval-ok` once audited.
- Recognizes `.csh` and `.tcsh` plus shebang sniffing of the first
  line; files invoked via an unconventional path won't be picked up
  in directory mode.

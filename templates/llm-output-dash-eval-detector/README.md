# llm-output-dash-eval-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** invocations of the dash `eval` builtin in `*.dash` files
(and any file with a `#!.../dash` or `#!/bin/sh` shebang — dash is
the default `/bin/sh` on Debian, Ubuntu, and Alpine).

## What it catches

dash (Debian Almquist Shell) is a small, strictly POSIX shell.
Like every POSIX shell, its `eval` builtin concatenates its
arguments with spaces and re-parses the result as shell input —
full word splitting, parameter expansion, command substitution,
redirection, the lot. When any argument is built from a `$var` /
`${var}`, a `$(cmd)` command substitution, or a backtick `` `cmd` ``
substitution, an attacker who controls that value gains arbitrary
shell execution. LLMs frequently emit `eval "$(curl -s "$url")"`
for "auto-configure from a remote endpoint" snippets — exactly the
shape this scanner exists to catch.

A purely literal `eval 'echo hello'` (single-quoted; no `$`,
`$(`, or `` ` ``) is **not** flagged. Suppress an audited line
with a trailing `# eval-ok` comment.

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — eight `.dash` files, each demonstrating one
  dynamic `eval` shape that should fire.
- `examples/good/` — five `.dash` files (literal eval, comment-only
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
`file:line:col: dash-eval-dynamic — <line>` per finding plus a
trailing `# N finding(s)` summary.

## Verification

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
  first physical line.
- Does not statically prove that `$var` is attacker-controlled — it
  only flags the dynamic surface. Triage findings against the
  source of each variable; suppress with `# eval-ok` once audited.
- Recognizes `.dash` plus shebang sniffing of the first line. The
  shebang sniffer also matches `#!/bin/sh` because that path is
  dash on most modern Debian-family distros — point the scanner at
  individual files explicitly if your `/bin/sh` is something else.

# llm-output-ksh-eval-detector

Pure-stdlib python3 single-pass scanner that flags KornShell
(ksh / ksh93) dynamic-code execution sinks (`eval`, `.` / `source`,
indirect `${!FOO}` name-references) in shell source files.

## What it detects

ksh has multiple ways to take a string and run it as code, all of
which are code-injection sinks when the string contains attacker-
or LLM-controlled data:

* `eval ARGS` — joins `ARGS` with spaces and re-parses the result
  as shell input. The single most common ksh injection sink.
* `command eval ARGS` / `builtin eval ARGS` / `exec eval ARGS` —
  same hazard wrapped in a builtin-discipline qualifier.
* `. FILE` (POSIX dot include) and `source FILE` (ksh/bash spelling)
  — read and execute `FILE` in the current shell. With a non-literal
  path this is arbitrary code by another name.
* `${!FOO}` indirect name-reference expansion — ksh looks up the
  *name* stored in `FOO` and dereferences that. Same hazard as
  `eval` over a variable name; an attacker who controls `FOO` can
  exfiltrate or smuggle any other variable.

LLM-emitted ksh reaches for `eval` to "build a command from
parts" or for `${!var}` to "look up a config value by name" —
almost always wrong. Safer alternatives:

* a `case "$op" in start) … ;; stop) … ;; esac` allowlist,
* an associative array (`typeset -A map; ... ${map[$key]}`) for
  data-driven dispatch,
* `printf -v varname "%s" "$value"` for assignment by computed
  name (does not re-parse).

## What this template gives you

* `detect.py` — single-pass scanner; pure python3 stdlib.
* `examples/bad/` — 7 positive cases (eval, command eval,
  builtin eval, dot include, source, indirect `${!FOO}`, eval
  after a pipe).
* `examples/good/` — 6 negative cases (allowlist dispatch, eval
  in comments, eval in strings, suppressed call, heredoc body,
  lookalikes `${#var}` / `$#` / `./foo`).
* `verify.sh` — end-to-end check: asserts `bad ≥ 6`, `good == 0`,
  and the detector exits with the conventional 1/0.

## Usage

```sh
python3 detect.py path/to/script.ksh
python3 detect.py path/to/dir/
```

Prints `path:line:col: ksh-eval — <stripped source line>` per
finding and a `# N finding(s)` summary. Exits 1 on any finding,
0 otherwise. Designed for pre-commit hooks and CI.

### Suppression

A trailing `# eval-ok` comment on the line silences a single
finding. Use sparingly and only when the argument is a static
literal under your control:

```sh
eval "$KNOWN_GOOD_CMD"  # eval-ok
```

## File-type detection

Scans files with `*.ksh` / `*.ksh93` extensions, plus any file
whose first line is a `#!…ksh…` shebang. Other shell dialects
(bash, dash, zsh, fish) are intentionally ignored — there are
sibling detectors for those where appropriate.

## Out of scope

* `trap '...' SIGNAL` — the trap body is also re-parsed by ksh,
  but signal-handler injection is a separate detector.
* `$(...)` and backticks — those are command substitution, not
  re-parsing of attacker data per se.
* `(( … ))` arithmetic with a string operand — ksh93 supports
  `$(( var ))` indirection that re-parses `var` as an
  expression, but this overlaps with the
  `llm-output-bash-eval-string-detector` arithmetic-injection
  rule and is left to a future refinement.

## Verify

```sh
./verify.sh
```

Expected output:

```
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
OK: ksh-eval detector verified (bad=7, good=0)
```

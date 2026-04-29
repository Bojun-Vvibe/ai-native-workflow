# llm-output-awk-system-detector

Single-pass python3 stdlib scanner that flags shell-command sinks in
AWK programs emitted by LLMs.

## What it detects

AWK exposes three ways to hand a string to `/bin/sh`:

* `system(cmd)`              — run `cmd`, return exit code
* `cmd | getline var`        — pipe-from: run `cmd`, read its stdout
* `print ... | cmd`          — pipe-to:   run `cmd`, write to its stdin
  (also `printf ... | cmd`)

In all three, the right-hand string is evaluated by the shell. When
that string is built from `$1`, `$0`, `ENVIRON[...]`, `ARGV[...]`,
or any field/variable derived from input, this is the AWK form of
`eval(user_input)` — a classic command-injection sink.

| Pattern | Kind |
| --- | --- |
| `system("literal string")` | `awk-system` (info) |
| `system(<anything else>)` | `awk-system-dynamic` |
| `<expr-not-bare-literal> | getline ...` | `awk-getline-pipe-from-dynamic` |
| `print ... | <expr-not-bare-literal>` | `awk-print-pipe-to-dynamic` |
| `printf ... | <expr-not-bare-literal>` | `awk-print-pipe-to-dynamic` |

A "bare literal" is a single `"..."` constant with no concatenation.
Anything that involves `$1`, a variable, `ENVIRON[]`, parentheses, or
string concatenation (`"a" b`) is treated as dynamic.

## False-positive notes

* Comments (`# ...`) and string contents are blanked out before
  matching, so doc-comments mentioning `system("rm " $1)` do not trip.
* Pure data transformations (`{ total += $2 }`) are silent.
* `cmd | getline` with `cmd` being a literal like `"date -u"` is
  considered safe by this detector — the command is fixed at author
  time. If you want to flag *all* shell-out, search the source for
  `getline` directly.
* `|&` (gawk co-process) is treated the same as `|`.

Suppression: append `# awk-exec-ok` on the line.

## Usage

```
python3 detector.py <file_or_dir> [<file_or_dir> ...]
```

Recurses into directories looking for `*.awk`, `*.gawk`, `*.mawk`,
and files whose first line is an awk/gawk/mawk shebang. Exit code `1`
if any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ python3 detector.py examples/bad examples/good
examples/bad/01_system_field.awk:3:3: awk-system-dynamic — { system("rm -rf " $1) }
examples/bad/02_pipe_from_dynamic.awk:5:3: awk-getline-pipe-from-dynamic — cmd | getline body
examples/bad/03_pipe_to_dynamic.awk:3:3: awk-print-pipe-to-dynamic — { print $0 | ("mailx -s subject " $3) }
examples/bad/04_env_system.awk:3:9: awk-system-dynamic — BEGIN { system("ls " ENVIRON["TARGET_DIR"]) }
examples/bad/05_printf_pipe_dynamic.awk:5:3: awk-print-pipe-to-dynamic — printf("%s\n", $0) | ("gzip -c > " outfile ".gz")
# 5 finding(s)
```

5 bad files produce 5 findings; 3 good files produce 0.

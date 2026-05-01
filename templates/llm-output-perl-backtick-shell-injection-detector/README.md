# llm-output-perl-backtick-shell-injection-detector

Static detector for Perl shell-injection footguns: backtick command
substitution, `qx//` operators, `system($cmd)` (single string),
`exec($cmd)`, and two-argument `open(FH, "...|")` /
`open(FH, "|...")` where the command string contains an interpolated
variable.

These are the canonical CWE-78 (OS Command Injection) shapes an LLM
emits when it just wants the script to "work":

```perl
my $log = `git log -- $path`;            # injection if $path = '; rm -rf /'
system("rm -rf $path/build");            # injection
open(my $fh, "git log $path|") or die;   # injection
```

The safe shape is always the **list form** of `system`, `exec`, and
the 3+ arg form of `open`:

```perl
system('git', 'log', '--', $path);                  # safe
open(my $fh, '-|', 'git', 'log', '--', $path);      # safe
```

## What this flags

Four related shapes:

1. **perl-backticks-interp** — a `` `...` `` string containing a
   `$var` / `@var` interpolation, OR `qx{...}`, `qx(...)`, `qx[...]`,
   `qx<...>`, `qx/.../`, `qx|...|`, `qx#...#`, `qx!...!`, `qx~...~`
   with the same.
2. **perl-system-string** — `system("...$x...")` or
   `system "...$x...";` (single string with interpolation). The list
   form is **not** flagged.
3. **perl-exec-string** — same shape for `exec`.
4. **perl-open-pipe-interp** — two-argument `open(FH, "...|")` /
   `open(FH, "|...")` where the mode/command contains a pipe and an
   interpolated variable.

A finding is suppressed if the same logical line carries
`# llm-allow:perl-shell`. Comments are masked before pattern matching;
single-quoted Perl strings are not interpolated and so are not flagged.

The detector also extracts fenced `pl` / `perl` code blocks from
Markdown.

## CWE references

* **CWE-78**: Improper Neutralization of Special Elements used in an
  OS Command (OS Command Injection).
* **CWE-88**: Improper Neutralization of Argument Delimiters.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/run.pl` and `examples/good/run.pl` for fixtures.

# llm-output-go-exec-command-injection-detector

Stdlib-only Python detector that flags **Go** source where `os/exec` is
invoked with a shell interpreter (`sh -c`, `bash -c`, `cmd /C`,
`powershell -Command`, etc.) **and** the script string is built from
`fmt.Sprintf`, string concatenation, or `strings.Join` over caller
input. This is the canonical CWE-78 (OS Command Injection) shape.

LLMs love to emit this exact pattern when a user says something like
"write a Go function that runs the command for me" — the model picks
`exec.Command("sh", "-c", fmt.Sprintf("...", arg))` because it looks
shorter than building an argv slice.

## Why "shell binary + dynamic script" specifically

Go's `exec.Command(name, args...)` is **not** vulnerable on its own:
each `args[i]` is passed as a separate argv entry to `execve(2)`, so
shell metacharacters are inert. The injection happens only when the
binary is itself a shell interpreter and the **next argument** is
parsed as script text. By looking for both halves we get a low
false-positive rate without needing a full Go parser.

## Heuristic

A finding is emitted when **all** of these hold for one call:

1. The call site is `exec.Command(...)` or `exec.CommandContext(ctx, ...)`.
2. The first non-context argument is one of:
   `sh`, `/bin/sh`, `/usr/bin/sh`, `bash`, `zsh`, `ksh`, `dash`,
   `cmd`, `cmd.exe`, `powershell`, `powershell.exe`, `pwsh`.
3. A subsequent argument is `"-c"`, `"/C"`, `"/c"`, `"-Command"`, or
   `"-EncodedCommand"`.
4. The argument **after** that flag contains at least one of:
   `fmt.Sprintf(`, `+ <ident>`, `<ident> +`, `strings.Join(`,
   `strings.Replace(`.

The argument splitter is a tiny hand-rolled tokenizer that respects
Go string literals (`"..."` and ``` `...` ```) and paren depth, so
nested calls like `fmt.Sprintf("a %s b", strings.Trim(x, " "))` parse
correctly.

## CWE / standards

- **CWE-78**: Improper Neutralization of Special Elements used in an OS Command.
- **CWE-77**: Improper Neutralization of Special Elements used in a Command (parent).
- **OWASP A03:2021** — Injection.

## Limits / known false negatives

- We don't follow variable assignments. If the script string is built
  earlier (`script := fmt.Sprintf(...); exec.Command("sh","-c",script)`)
  the call-site arg is just `script`, which lacks our dynamic-hint
  markers and won't trip. (Variable-flow tracking is out of scope for a
  stdlib-only single-file detector.)
- `bash -lc`, `bash --login -c`, and other less-common flag spellings
  are not currently recognized.
- We do not flag `syscall.Exec`, `os.StartProcess`, or `cgo` shells.

These are deliberate trade-offs to keep false positives near zero on
hand-written Go.

## Usage

```bash
python3 detect.py path/to/file.go
python3 detect.py path/to/dir/   # walks *.go and *.go.txt
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_sprintf.go            # sh -c + fmt.Sprintf
  02_concat.go             # bash -c + "+"
  03_commandcontext.go     # CommandContext + concat
  04_strings_join.go       # sh -c + strings.Join
  05_cmd_exe.go            # cmd.exe /C + concat
  06_powershell.go         # powershell -Command + Sprintf
examples/good/
  01_argv_form.go          # cat <filename> argv
  02_shell_constant_script.go   # sh -c with literal script
  03_ping_argv.go          # ping argv form
  04_git_argv.go           # CommandContext non-shell binary
  05_git_checkout.go       # variable as argv entry, not as script
  06_powershell_literal.go # powershell with literal script
```

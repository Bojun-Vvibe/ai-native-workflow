# llm-output-vimscript-execute-detector

Pure-stdlib python3 single-pass scanner that flags dynamic
`:execute` / `:exec` / `:exe` Ex commands and `eval(...)` function
calls in Vim script.

## What it detects

In Vim script, `:execute STR` builds an Ex command from STR and runs
it; `eval(STR)` parses STR as a Vim-script expression and returns its
value. Both are dynamic-code sinks: any caller-controlled fragment
spliced into STR becomes runnable Vim script — same blast radius as
`system($USER_INPUT)` in shell.

LLM-emitted Vim plugins reach for `:execute` to "build a command from
variables" (e.g. `:execute 'normal' a:keys`). The safe forms are:

* `feedkeys(s, 'n')` for keystroke replay (escapes are explicit), or
* a plain Ex command with literal arguments, or
* `:call FN(arg)` for invoking a known function.

## What gets scanned

* Files with extension `.vim`, `.vimrc`.
* Files literally named `vimrc`, `.vimrc`, `_vimrc`, `gvimrc`,
  `.gvimrc`.
* Files whose first line contains `vim:` (modeline) or starts with
  `" Vim`.
* Directories are recursed.

## False-positive notes

* `"`-comments at command position and string contents (`"..."`,
  `'...'` with `''` escape) are masked out before scanning, so
  occurrences inside strings or comments are never flagged.
* A user function literally named `evaluate_user_input` is NOT
  flagged — the regex requires `\beval\s*\(`.
* Method-style `:execute` is the dangerous one we want; `:source`,
  `:runtime`, `:luaeval`, `py3eval` are out of scope.
* Suppress an audited line with a trailing `" exec-ok` comment.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: vim-execute|vim-eval — <stripped source line>
# <N> finding(s)
```

## Worked example

```
$ python3 detect.py examples/bad.vim
examples/bad.vim:5:3: vim-execute — execute 'edit ' . a:fname
examples/bad.vim:9:3: vim-execute — exe "normal! " . a:keys
examples/bad.vim:13:4: vim-execute — :exec a:cmd
examples/bad.vim:17:11: vim-eval — let v = eval(a:expr)
examples/bad.vim:22:15: vim-execute — let x = 1 | execute 'echo ' . a:cmd
examples/bad.vim:26:19: vim-eval — call setline(1, eval(s:s))
# 6 finding(s)

$ python3 detect.py examples/good.vim
# 0 finding(s)
$ echo $?
0
```

`examples/bad.vim` has 6 expected findings (4 `vim-execute`,
2 `vim-eval`). `examples/good.vim` has 8 deliberately-tricky shapes
(literal Ex commands, `feedkeys` replacement, `evaluate_user_input`
look-alike, `eval` inside string literals and `"`-comments, and an
audited `" exec-ok`-suppressed line) — all must produce zero findings.

## Why this matters

`:execute 'edit ' . a:fname` looks innocuous in a code-review diff but
is the exact shape that lets `a:fname = "scratch | !rm -rf ~"` pivot
into shell. The only general fix is to stop building Ex commands from
strings; this detector forces that conversation at PR time instead of
post-incident.

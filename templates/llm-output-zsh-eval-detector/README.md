# llm-output-zsh-eval-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** Zsh `eval` / `print -z` / `${(e)var}` constructs in
`*.zsh`, `.zshrc`, `.zshenv`, `.zprofile`, `.zlogin`, `.zlogout`
files (and any file with a `#!.../zsh` shebang).

## Why this matters for LLM-generated zsh

LLMs reach for `eval` whenever they want to "build a command then run
it" — e.g. composing `git`, `kubectl`, `ssh`, or `find` invocations
from variables. In zsh, three forms collapse the boundary between
data and code:

1. `eval $cmd` / `eval "$cmd"` — `$cmd` is re-parsed as shell
   source. Double quotes do **not** disarm it; double quotes only
   suppress word-splitting, not expansion.
2. `print -z $cmd` — pushes `$cmd` onto the line-editor buffer
   (ZLE). In a widget, the next user keypress executes it. This is
   eval with one extra keystroke.
3. `${(e)var}` — the `(e)` parameter-expansion flag forces a
   **second** eval pass on `var`'s value. So `${(e)template}` where
   `template='hello $(id)'` runs `id`. This is the form that almost
   never gets caught in code review because it looks like a normal
   parameter expansion.

## What this flags

| construct                                        | flagged? |
| :----------------------------------------------- | :------: |
| `eval $cmd`                                      | yes      |
| `eval "echo $header"`                            | yes      |
| `eval "$(curl ...)"`                             | yes      |
| ``eval `git config ...` ``                       | yes      |
| `eval $cmd` (after `then`, `else`, `do`, `;`, `\|`) | yes   |
| `print -z $suggested`                            | yes      |
| `${(e)template}`                                 | yes      |
| `eval 'set -- a b c'` (purely literal)           | NO       |
| `eval "set -o pipefail"` (purely literal)        | NO       |
| `print -z 'help text'`                           | NO       |
| `${(U)var}`, `${(L)var}`, `${(P)var}`            | NO       |

"Dynamic" means the argument contains a `$` or `` ` `` after string-
content masking. Single-quoted literals are inert (no expansion in
zsh) and are masked out before scanning, so a literal mention of
`'eval $foo'` in a documentation string is not flagged.

## What gets scanned

* Files with extension `.zsh`.
* Files named `.zshrc`, `.zshenv`, `.zprofile`, `.zlogin`,
  `.zlogout` (and the dotless variants).
* Files whose first line is a shebang containing `zsh`.
* Directories are recursed.

## False-positive notes

* `#`-comment tails are masked out.
* `'...'` literal contents are masked out (single quotes are inert
  in zsh).
* `"..."` literal contents are masked too, but `$` and `` ` `` and
  `$(` inside double quotes are preserved — that mirrors the shell's
  own behaviour (double quotes do NOT prevent expansion) and is what
  makes `eval "echo $header"` correctly flagged.
* Identifiers that merely contain `eval` (`evaluate`, `my_eval_helper`)
  are not flagged — the regex requires a `\beval\b` token at command
  position.
* `print` without `-z` is not flagged.
* `${(...)var}` flag forms that do not include `e` (`(U)`, `(L)`,
  `(P)`, `(o)`, etc.) are not flagged.
* `# eval-ok` on a line suppresses that line.

## Out of scope (deliberately)

* `source` / `.` of a dynamic path — different sink, sibling
  detector.
* `zsh -c "$cmd"` — covered by the bash-eval-string detector family.
* Building shell command strings to hand to `system(3)` from C — not
  a zsh source-level concern.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: zsh-{eval-dynamic|print-z-dynamic|parexp-e-flag} — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad
examples/bad/01_eval_var.zsh:4:1: zsh-eval-dynamic — eval $cmd
examples/bad/02_eval_quoted.zsh:6:1: zsh-eval-dynamic — eval "echo $header; echo $body"
examples/bad/03_eval_cmdsub.zsh:3:1: zsh-eval-dynamic — eval "$(curl -fsSL https://example.invalid/install.sh)"
examples/bad/04_eval_backtick.zsh:3:1: zsh-eval-dynamic — eval `git config --get alias.$1`
examples/bad/05_eval_after_then.zsh:3:24: zsh-eval-dynamic — if [[ -n $cmd ]] then; eval $cmd; fi
examples/bad/06_print_z_dynamic.zsh:6:1: zsh-print-z-dynamic — print -z $suggested
examples/bad/07_parexp_e_flag.zsh:6:8: zsh-parexp-e-flag — result=${(e)template}
examples/bad/08_eval_after_pipe.zsh:4:11: zsh-eval-dynamic — get_cmd | eval "$(cat)"
# 8 finding(s)

$ python3 detect.py examples/good
# 0 finding(s)
```

bad: **8** findings, good: **0** findings. PASS.

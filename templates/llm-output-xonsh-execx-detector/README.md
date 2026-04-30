# llm-output-xonsh-execx-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** xonsh `execx` / `evalx` (and their lower-level
`__xonsh__.execer.exec` / `__xonsh__.execer.eval`) calls in `*.xsh`
files, `.xonshrc`, and any file whose first line is a xonsh shebang.

## Why this matters for LLM-generated xonsh

xonsh is a Python-powered shell: any line is either Python or a
shell command, and the two interleave freely. That makes xonsh a
favorite target for LLMs that want to "do shell stuff in Python."
But xonsh's `execx(SOURCE)` builtin re-parses SOURCE as fresh
xonsh — i.e. mixed Python + shell — and runs it in the current
namespace. So a single `execx(user_input)` is simultaneously:

* a Python `exec` (arbitrary Python in your namespace), and
* a shell `eval` (arbitrary OS commands via xonsh's subprocess
  syntax).

That is strictly worse than either eval alone, and the failure mode
LLMs reach for ("just `execx` the string we built") shows up
constantly when they translate bash recipes into xonsh.

## What this flags

| construct                                         | flagged? |
| :------------------------------------------------ | :------: |
| `execx(cmd)`                                      | yes      |
| `execx(f"git push {target}")`                     | yes      |
| `execx("ls " + path)`                             | yes      |
| `execx(template.format(workdir, target))`         | yes      |
| `execx("kubectl --context=%s apply" % ctx)`       | yes      |
| `execx($USER_SCRIPT)`                             | yes      |
| `evalx($(echo $QUERY))`                           | yes      |
| `__xonsh__.execer.exec(src)`                      | yes      |
| `execx("echo hello")` (purely literal)            | NO       |
| `evalx("1 + 2")` (purely literal)                 | NO       |
| `"use execx(SOURCE) to ..."` (word inside string) | NO       |

Trigger conditions for "dynamic" inside the call argument, evaluated
on the comment+string-scrubbed slice:

* xonsh sigils: `$`, `@(`, `![`, `!(`
* python f-string prefix `f"` / `f'`
* `.format(`, `%`-formatting, `+` concatenation
* any bare identifier reference (variable name) other than
  `True` / `False` / `None` / python keywords

## Suppression

Append `# execx-ok` to the call's line after manual review.

## Usage

```sh
python3 detect.py path/to/script.xsh
python3 detect.py examples/bad examples/good
```

Exit code is `1` if any findings, `0` otherwise. Findings look like:

```
examples/bad/02_fstring.xsh:3:1: xonsh-execx-dynamic — execx(f"git push origin {target}")
```

## Worked example

```sh
./verify.sh
```

Asserts `examples/bad/` produces ≥7 findings and `examples/good/`
produces 0. Exits 0 on PASS.

## Known limits

* Multi-line `execx(` calls where the dynamic argument starts on a
  later line are still detected (we walk balanced parens), but the
  reported column is the line of the call name, not the offending
  argument fragment. That is consistent with the rest of the
  detector family.
* Scope-aware analysis ("but `cmd` is hard-coded three lines up")
  is out of scope. The rule is: if the literal source of the call
  contains a dynamic-looking arg, audit it.
* Plain Python `eval(` / `exec(` are NOT covered here on purpose;
  use the python-eval-string detector for those. xonsh files that
  also use `exec()` will still be picked up by that sibling.

## Why python3 stdlib only

Same constraints as the rest of the `llm-output-*-detector` family:
zero install footprint, runs anywhere a recent python is on PATH,
trivial to vendor into a CI step.

# llm-output-elvish-eval-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** Elvish `eval` invocations in `*.elv` source files (and any
file with a `#!.../elvish` shebang).

## Why this matters for LLM-generated elvish

Elvish (https://elv.sh) is a structured shell with a friendly
pipeline syntax that makes the dangerous form especially easy to
write. The builtin `eval` accepts a string and runs it as fresh
elvish source:

```elv
eval $code                                # variable expansion
eval (slurp < $path)                      # file-driven eval
eval (curl -fsSL $url | slurp)            # remote eval
eval "echo "$header                       # built from a $var
```

When the argument is built from a variable or an output-capture, an
attacker who controls that value gets full elvish-runtime execution:
arbitrary external commands, filesystem writes, environment mutation,
keybinding installation, etc. The blast radius is identical to
`bash eval`.

LLMs reach for `eval` whenever they are asked to "run a remote
installer", "execute a snippet from a config file", or "let the user
type a one-liner". All three idioms collapse the data/code boundary.

## What this flags

| construct                                     | flagged? |
| :-------------------------------------------- | :------: |
| `eval $code`                                  | yes      |
| `eval (curl ... \| slurp)`                    | yes      |
| `eval (slurp < $path)`                        | yes      |
| `eval "echo "$header`                         | yes      |
| `eval 'echo hello '$name`                     | yes      |
| `eval $code` (after `;`, `\|`, `{`, `(`)      | yes      |
| `eval "set-env FOO bar"` (purely literal)     | NO       |
| `eval 'put hello'` (purely literal)           | NO       |

"Dynamic" means the argument contains a `$`, `` ` ``, or `(` after
string-content masking. `'...'` literals are inert in elvish (no
expansion, no re-evaluation) and are masked out before scanning, so
documentation strings that mention `'eval $foo'` are not flagged.

## What gets scanned

* Files with extension `.elv`.
* Files whose first line is a shebang containing `elvish`.
* Directories are recursed.

## False-positive notes

* `#`-comment tails are masked out.
* `'...'` single-quoted contents are masked out (single quotes are
  fully literal in elvish; `''` is the escape for a literal single
  quote and is handled).
* `"..."` double-quoted contents are masked too, EXCEPT for `$`,
  `` ` ``, and `(` — those are preserved so that
  `eval "echo "$header` is correctly flagged. Elvish's own double
  quotes do not interpolate, but `eval` re-parses the string in a
  second pass where any embedded `$var` literally written into the
  string DOES become a real expansion.
* Identifiers that merely contain `eval` (`evaluate-score`,
  `my-eval-helper`, `eval-result`) are not flagged — the regex
  requires a `\beval\b` token at command position.
* `# eval-ok` on a line suppresses that line.

## Out of scope (deliberately)

* `use` with a dynamic module name — different sink, sibling
  detector candidate.
* `e:cmd $arg` — running an external with attacker args is a
  separate (well-known) shell-injection family.
* `src` / `-source` flag of `elvish` invoked from outside Elvish.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: elvish-eval-dynamic — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad
examples/bad/01_eval_var.elv:4:1: elvish-eval-dynamic — eval $code
examples/bad/02_eval_capture.elv:4:1: elvish-eval-dynamic — eval (curl -fsSL https://example.invalid/install.elv | slurp)
examples/bad/03_eval_slurp.elv:5:1: elvish-eval-dynamic — eval (slurp < $path)
examples/bad/04_eval_dq_interp.elv:6:1: elvish-eval-dynamic — eval "echo "$header
examples/bad/05_eval_after_pipe.elv:3:30: elvish-eval-dynamic — echo $user-supplied-script | eval (slurp)
examples/bad/06_eval_in_lambda.elv:5:28: elvish-eval-dynamic — var run-snippet = { |code| eval $code }
examples/bad/07_eval_after_semi.elv:3:19: elvish-eval-dynamic — var x = 'put hi'; eval $x
examples/bad/08_eval_concat.elv:5:1: elvish-eval-dynamic — eval 'echo hello '$name
# 8 finding(s)

$ python3 detect.py examples/good
# 0 finding(s)
```

bad: **8** findings, good: **0** findings. PASS.

# llm-output-bash-eval-string-detector

Pure-stdlib python3 single-pass scanner that flags `eval STRING` calls
in bash/sh/zsh source files.

## What it detects

`eval` in shell recompiles its argument as shell source and executes
it in the current shell. Any variable, command substitution, or
user-controlled fragment that flows into `eval` is a code-injection
sink with the same blast radius as `system($USER_INPUT)`.

LLM-emitted shell scripts reach for `eval` to "expand a variable that
holds a command" — almost always wrong; arrays (`"${cmd[@]}"`), a
`case` dispatcher, or `bash -c -- "$script" placeholder "$arg"` are
the safe alternatives.

The detector flags `eval` at statement position, regardless of whether
the argument is quoted, interpolated, or literal — `eval` itself is
the smell. Suppress an audited line with a trailing `# eval-ok`
comment.

## What gets scanned

* Files with extension `.sh`, `.bash`, `.zsh`.
* Files whose first line is a shebang containing `bash`, `/sh`, `zsh`,
  `ksh`, or `dash`.
* Directories are recursed.

## False-positive notes

* `eval` inside a comment or inside a `"..."` / `'...'` literal that
  is *not itself* the argument to `eval` is masked out before scanning.
* `# eval-ok` on a line suppresses that line entirely.
* The detector does not try to prove a string is constant — string-eval
  with no interpolation is still a smell worth a human glance, so
  literal-string `eval 'echo x'` is flagged. Add `# eval-ok` if it's
  intentional.
* Shell here-docs are not separately tracked; an `eval` literally
  appearing inside a heredoc body that quoted the terminator (`<<'EOF'`)
  could in principle false-positive. In practice LLM output rarely
  triggers this; treat any flagged heredoc line as a real finding
  worth a human glance.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: eval-string — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad.sh
examples/bad.sh:7:1: eval-string — eval "$cmd"                                # 1: variable into eval
examples/bad.sh:10:1: eval-string — eval $action                                # 2: unquoted variable into eval
examples/bad.sh:12:10: eval-string — result=$(eval "$(cat /tmp/payload.sh)")     # 3: command substitution into eval
examples/bad.sh:17:1: eval-string — eval "deploy_$target --force"           # 4: interpolated string
examples/bad.sh:22:1: eval-string — eval 'echo hello world'                     # 5: literal-string eval
examples/bad.sh:25:24: eval-string — if [ -n "$cmd" ]; then eval "$cmd"; fi      # 6: after `then`
examples/bad.sh:26:8: eval-string — true && eval "$cmd"                         # 7: after &&
examples/bad.sh:27:2: eval-string — { eval "$cmd"; }                            # 8: inside brace group
# 8 finding(s)

$ python3 detect.py examples/good.sh
# 0 finding(s)
```

bad: **8** findings, good: **0** findings.

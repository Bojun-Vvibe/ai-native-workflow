# llm-output-shell-unquoted-variable-detector

Pure-stdlib, code-fence-aware detector that flags **unquoted shell
variable expansions** (`$var`, `${var}`, `$(cmd)`) in fenced
shell code blocks emitted by an LLM.

Unquoted expansions in POSIX shell are a well-known foot-gun: when
the value contains spaces, globs, or is empty, the shell performs
word-splitting and pathname expansion. `rm -rf $dir` when `dir`
is empty becomes `rm -rf` (no-op, lucky); `cp $src $dst` when
`src` contains a space copies two wrong files. LLMs frequently
emit unquoted expansions in "copy-paste this" snippets because
the training corpus is full of them. This detector flags them at
emit time so the snippet can be re-prompted before a user runs it.

## What it flags

| kind | meaning |
|---|---|
| `unquoted_var` | `$name` or `${name}` not inside single or double quotes |
| `unquoted_cmdsub` | `$(...)` not inside single or double quotes |

Recognized fence info-string tags (case-insensitive):
`sh`, `bash`, `shell`, `zsh`, `ksh`, `posix`.

## Out of scope (deliberately)

- Backtick command substitution and arithmetic `$((...))`.
- Special parameters: `$?`, `$$`, `$#`, `$@`, `$*`, `$!`, `$0`..`$9`,
  `$-`, `$_` (these are syntactically distinct or never need quoting
  for word-splitting safety).
- The RHS of a bare assignment (`var=$other`, including `export`,
  `local`, `readonly`, `declare`, `typeset`) — conventionally fine.
- Heredoc bodies (`<<EOF` / `<<-EOF`) are skipped; their contents
  are data, not commands.
- Comments (`#` to end of line) are skipped.

This is a *first-line-defense* sniff test, not a shellcheck
replacement.

## Usage

```
python3 detect.py <markdown_file>
```

Stdout: one finding per line, e.g.

```
block=1 line=3 col=8 kind=unquoted_var token=$dir
```

Stderr: `total_findings=<N> blocks_checked=<M>`.

Exit codes:

| code | meaning |
|---|---|
| `0` | no findings |
| `1` | at least one finding |
| `2` | bad usage |

## Worked example

Run against the bundled examples:

```
$ python3 detect.py examples/bad.md
block=1 line=3 col=8 kind=unquoted_var token=$dir
block=1 line=4 col=4 kind=unquoted_var token=$src
block=1 line=4 col=9 kind=unquoted_var token=$dst
block=1 line=5 col=6 kind=unquoted_cmdsub token=$(whoami)
block=1 line=8 col=10 kind=unquoted_var token=${files}
block=1 line=12 col=12 kind=unquoted_var token=${log}
# stderr: total_findings=6 blocks_checked=3
# exit: 1

$ python3 detect.py examples/good.md
# stderr: total_findings=0 blocks_checked=2
# exit: 0
```

Three blocks are scanned in `bad.md`: the bash example block, the
heredoc block (body skipped, only the visible `cat <<EOF` line is
considered — no expansions on it), and the comment-only bash block.
Two are scanned in `good.md`: bash and sh; the python block is
ignored because its language tag is not in the recognized set.

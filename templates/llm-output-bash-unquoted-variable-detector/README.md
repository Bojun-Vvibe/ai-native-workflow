# llm-output-bash-unquoted-variable-detector

A small Python 3 stdlib sniffer for shell scripts where a `$var`,
`${var}`, `$(cmd)`, or `` `cmd` `` expansion appears outside of any
quotes in a context that would word-split or glob-expand it.

## Why it matters for LLM-generated output

Unquoted expansions are the #1 cause of "works on my laptop, breaks in
CI" failures. With one space in a path, one star in a filename, or one
empty value:

```bash
SRC=$1
cp $SRC /tmp/dst        # path with space -> two args -> wrong file copied
rm $LOGS                # $LOGS empty -> "rm" with no args -> usage error
                        # $LOGS = "* ."   -> rm everything in cwd
```

LLMs frequently emit unquoted expansions because they read more cleanly
and most tutorial snippets do the same. ShellCheck (`SC2086`) catches
this, but ShellCheck is heavyweight; this template is meant for fast
pre-commit / LLM-output review hooks where shipping a Haskell binary
is too much.

## Rule

Scan each line and build a per-character "quote state" vector that knows
whether each position is inside `"..."`, `'...'`, `[[ ... ]]`, or
`(( ... ))` / `$(( ... ))`. Then for every `$var` / `${var}` / `$(cmd)`
/ `` `cmd` `` match, flag it if and only if it sits in the default
state (no quotes, not in `[[ ]]`, not in arithmetic).

### Whitelist (intentionally NOT flagged)

- Right-hand side of a simple `var=$other` assignment — bash treats
  this as if quoted (no word-splitting, no globbing).
- Inside `[[ ... ]]` — bash also disables word-splitting there.
- Inside arithmetic `(( ... ))` or `$(( ... ))`.
- Numeric / special expansions: `$?`, `$#`, `$$`, `$!`, `$0..$9` —
  no splitting concern in practice.
- Inside a heredoc body (best-effort tracker via `<<EOF` / matching
  terminator line).
- Comment lines (start with `#`) and trailing `# ...` comments.

## Limitations

- Heuristic, not a shell parser. Won't understand `eval` chains, shell
  functions invoked with their own quoting conventions, or unusual
  here-doc indentation rules.
- Per-line state: doesn't track quotes that span lines via backslash
  continuation. In practice multi-line strings in bash use heredocs,
  which are handled.
- Outer command-substitution swallows inner unquoted expansions in the
  finding output (one finding per outer `$(...)` rather than one per
  nested `$var`). This is a feature: fixing the outer site fixes the
  inner ones.

## Usage

```
python3 detector.py <file.sh> [<file.sh> ...]
```

Prints `path:line: unquoted expansion <token>: <text>` for each
violation, then a trailing `findings: N` line. Exit code equals the
finding count (capped at 255).

## Worked example

```
$ python3 detector.py examples/bad.sh
examples/bad.sh:11: unquoted expansion $SRC: cp $SRC $DST
examples/bad.sh:11: unquoted expansion $DST: cp $SRC $DST
examples/bad.sh:14: unquoted expansion $(find . -name '*.txt' | head -1): echo Found: $(find . -name '*.txt' | head -1)
examples/bad.sh:18: unquoted expansion $NAME: if [ -n $NAME ]; then
examples/bad.sh:19: unquoted expansion $NAME: echo hi $NAME
examples/bad.sh:23: unquoted expansion $(ls $SRC): for f in $(ls $SRC); do
examples/bad.sh:24: unquoted expansion $f: echo processing $f
examples/bad.sh:29: unquoted expansion $HOST: echo connecting to $HOST
examples/bad.sh:32: unquoted expansion $DST: cat > $DST/log.txt <<EOF
findings: 9

$ python3 detector.py examples/good.sh
findings: 0
```

`examples/good.sh` is the same script rewritten with quoted expansions,
`[[ ]]` for tests, and a glob (`"$SRC"/*`) instead of `$(ls $SRC)`. It
also exercises every whitelist branch so a regression in the quote-state
machine surfaces immediately.

# llm-output-sed-e-flag-detector

Single-pass detector for the GNU sed **`s///e` execute flag** and the
standalone **`e COMMAND`** sed command. Both forms hand the
substitution result (or a literal string) to `/bin/sh -c`, turning a
"text rewrite" into shell execution. When the substituted text comes
from a captured group, the pattern space, or any LLM/user-controlled
source, this is shell injection.

## Why this exists

LLM-generated shell snippets occasionally look like:

```sh
echo "host=$USER" | sed 's/host=\(.*\)/echo \1/e'
```

The author's mental model is "rewrite the line and print it." The
actual semantics is "fork `/bin/sh -c "echo $USER"`." Reviewers
skimming for `eval`, `system`, `exec`, `xargs sh -c` will miss this
because it hides inside what looks like a substitution.

This detector surfaces every occurrence so a human can decide.

## What it flags

| Construct                       | Why                                       |
| ------------------------------- | ----------------------------------------- |
| `s/PAT/REPL/e`                  | Replacement is shell-executed             |
| `s|x|y|gie`, `s#a#b#Me`         | Same flag, different delimiter / siblings |
| `e COMMAND` (standalone)        | Executes COMMAND, inserts stdout          |
| Address + e: `2e uname -a`      | Same as above, address-scoped             |

## What it ignores

- Substitutions without `e` (`s/foo/bar/g`, `s|a|b|I`, …).
- `awk system()`, shell `eval`, perl `s///e` — covered by their own
  detectors in this repo.
- Lines marked with the suppression comment `# sed-e-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies.

Recurses into directories looking for `*.sed`, `*.sh`, `*.bash`,
`*.zsh`, `*.ksh`, and any file whose shebang names `sed`, `bash`,
`/sh`, `zsh`, or `ksh`.

## Verified output

Run against the bundled examples:

```
$ python3 detect.py examples/bad.sh
examples/bad.sh:8:32: sed-s-e-flag — echo "host=$USER_INPUT" | sed 's/host=\(.*\)/echo \1/e'
examples/bad.sh:11:27: sed-s-e-flag — echo "$USER_INPUT" | sed 's|^|date +%s; |gie'
examples/bad.sh:14:9: sed-s-e-flag — sed -e 's#FOO#whoami#e' input.txt
examples/bad.sh:18:1: sed-e-command — sed -i -e '/MARKER/e cat /etc/passwd' notes.txt
examples/bad.sh:21:1: sed-e-command — echo bar | sed '2e uname -a'
# 5 finding(s)

$ python3 detect.py examples/good.sh
# 0 finding(s)
```

## Design notes

- **Single pass per line**, two compiled regexes, comment + shell
  string-quote masking before matching to keep false positives down
  on prose like `users/admin/role/edit`.
- Sed-native files (`*.sed` or sed shebang) get sed-style `#`
  comment scrubbing; shell hosts get quote-span isolation so we only
  scan inside `'...'` and `"..."` (which is where sed scripts
  legitimately live in shell pipelines).
- Suppression marker `# sed-e-ok` lets you whitelist a single line
  when execution is intentional and the input is trusted.

## Layout

```
detect.py            # the scanner
examples/bad.sh      # five intentional violations
examples/good.sh     # zero violations, including a suppressed line
```

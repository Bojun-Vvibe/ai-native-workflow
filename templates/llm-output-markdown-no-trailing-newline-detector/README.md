# llm-output-markdown-no-trailing-newline-detector

Detects Markdown files that do not end with a single trailing newline (`\n`).

## Why this matters for LLM outputs

LLM token streams almost always stop on a content token, not a newline.
When agents write the streamed text to disk verbatim, the resulting file
ends mid-line. Symptoms:

- POSIX tools (`cat`, `wc -l`, `diff`) treat the last line as "incomplete"
  and either suppress it, miscount it, or print `\ No newline at end of file`.
- `git diff` annotates the file with a permanent `\ No newline at end of file`
  marker, which clutters every future PR that touches the bottom of the file.
- Concatenating two such files produces a glued line: the last line of the
  first file fuses with the first line of the second.
- Some Markdown renderers drop the final paragraph entirely.

It also flags the opposite extreme — *multiple* trailing newlines (blank
lines at EOF), which create spurious diff churn.

## What it does

Reads the file as bytes and inspects the tail:

- empty file → OK (exit 0)
- last byte is not `\n` → flag "missing trailing newline"
- ends with two or more `\n` → flag "extra trailing blank lines"
- exactly one trailing `\n` → OK

Exit code: `1` on any flag, else `0`.

## Run

```
python3 detect.py path/to/file.md
python3 detect.py examples/bad.md   # exits 1
python3 detect.py examples/good.md  # exits 0
```

Stdlib only, Python 3.8+. Treats CR/LF endings transparently (a final `\r\n`
is accepted as a proper terminator).

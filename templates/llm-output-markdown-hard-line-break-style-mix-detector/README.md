# llm-output-markdown-hard-line-break-style-mix-detector

Detects when a Markdown document mixes more than one **hard line break**
style. The three styles are:

1. **Trailing two-or-more spaces** at end of line — CommonMark canonical.
2. **Trailing backslash** `\` at end of line — CommonMark alternate.
3. **Inline `<br>` HTML tag** — `<br>`, `<br/>`, `<br />`.

All three render to the same `<br>` in HTML, but mixing them inside a
single document is a typical low-grade quality smell of LLM output
patched together from different prompts or sources.

## What it does

- Walks the file line by line, tracking fenced code blocks (` ``` ` /
  ` ~~~ `) so candidates inside them are ignored.
- Strips inline code spans so `<br>` inside backticks doesn't trip
  the detector.
- Counts each style. A trailing-spaces or trailing-backslash mark
  only counts if the *next* line is non-blank, matching CommonMark
  semantics (otherwise it's just trailing whitespace, not a hard
  break).
- Exits 1 when 2 or more distinct styles are present, 0 otherwise.

## Usage

```sh
python3 detect.py path/to/file.md
```

## Exit codes

| code | meaning                                                |
|------|--------------------------------------------------------|
| 0    | clean — at most one hard-break style present           |
| 1    | mix detected — two or three distinct styles present    |
| 2    | usage error                                            |

## Examples

```sh
python3 detect.py examples/bad.md ; echo "exit=$?"
python3 detect.py examples/good.md ; echo "exit=$?"
```

## Output format

```
file: examples/bad.md
hard-break occurrences: trailing-spaces=2, trailing-backslash=1, br-tag=2
MIX DETECTED: 3 distinct hard-break styles in same document
  line  3 [trailing-spaces]: '   '
  line  5 [trailing-backslash]: 'end.\\'
  line  7 [br-tag]: <br>
  ...
```

## Dependencies

Python 3 stdlib only.

## Limitations

- Trailing-whitespace-only lines (no other content) are skipped — they
  are not hard breaks regardless of style.
- Does not validate that a hard break is *desired* at any given
  location; only flags inconsistent style.
- Escaped backslashes (`\\`) at line end are not counted as hard
  breaks.

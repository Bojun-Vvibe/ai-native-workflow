# llm-output-markdown-blank-line-before-heading-consistency-validator

Validate that every ATX heading is preceded by a blank line.

CommonMark renders ATX headings correctly even when they sit flush
against the previous paragraph, but most style guides (and
`markdownlint` rule MD022) require a blank line above each heading.
This avoids edge-case render bugs in some renderers and keeps the
source readable.

LLMs commonly emit headings with no blank line above them, especially
when streaming output after a paragraph, list, or code block.

## What it flags

Every ATX heading (lines starting with 1-6 `#` followed by space)
whose immediately preceding line is non-blank — except for the first
non-blank line of the document, which has nothing to be separated from.

## What it does not flag

- The first non-blank line of the document, even if it's a heading
- Setext headings (`===` / `---` underlines)
- `#`-prefixed lines inside fenced code blocks (` ``` ` or `~~~`)
- `#`-prefixed lines inside indented code blocks (4+ leading spaces)
- Missing blank line *after* a heading (a separate concern)

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` if any flagged heading is found, `0` otherwise.

## Verify against the worked example

Bad input (intentional violations):

```
$ python3 script.py < worked-example/input.md
line 4: heading not preceded by blank line: '## Background'
line 7: heading not preceded by blank line: '### Details'
line 14: heading not preceded by blank line: '#### Wrap-up'
$ echo $?
1
```

Clean input:

```
$ python3 script.py < worked-example/clean.md
$ echo $?
0
```

You can also diff against the recorded expected output:

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff.

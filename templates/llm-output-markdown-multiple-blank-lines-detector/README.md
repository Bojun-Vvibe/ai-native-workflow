# llm-output-markdown-multiple-blank-lines-detector

Detect runs of two or more consecutive blank lines outside fenced code
blocks. CommonMark collapses any run of consecutive blank lines into a
single paragraph break, so multiple blanks in source are pure noise — they
inflate diffs, break some renderers, and trigger markdownlint MD012.

LLMs commonly emit doubled or tripled blank lines when stitching
sections together (especially around headings, lists, and code blocks),
because each section was generated with its own trailing blank line.

## What it flags

Every run of `>=2` consecutive blank lines that occurs **outside** a
fenced code block. A "blank" line is one that is empty or contains only
whitespace.

## What it does not flag

- A single blank line between blocks (the normal case).
- Blank lines **inside** ` ``` ` or `~~~` fenced code blocks (those carry
  meaning — they are part of the code).
- Tab-only or space-only lines inside a fence (same reason).

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` if any run of `>=2` blank lines is found, `0` otherwise.

## Verify against the worked example

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff. The script itself exits `1` because the worked
example contains three intentional findings (a 3-blank-line run, a
2-blank-line run, and a 4-blank-line run; the blank lines inside the
fenced code block are correctly ignored).

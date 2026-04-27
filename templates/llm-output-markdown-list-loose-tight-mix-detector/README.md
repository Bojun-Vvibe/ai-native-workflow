# llm-output-markdown-list-loose-tight-mix-detector

Detect markdown lists where some items are separated by blank lines (loose
form) and others are not (tight form). CommonMark renders loose-form items
inside `<p>` tags, producing visibly different vertical spacing — so mixed
spacing within a single list reads as inconsistent.

LLMs frequently emit lists like:

```
- First item
- Second item

- Third item, with blank line above
- Fourth item
```

…where the blank line is unintentional and produces uneven rendering.

## What it flags

For every list group of two or more items at the same indent level, if at
least one adjacent pair is separated by a blank line and at least one pair
is not, the script reports the line range and the count of loose vs tight
pairs.

## What it does not flag

- Lists that are uniformly tight (no blank lines between items)
- Lists that are uniformly loose (every item separated by a blank line)
- Single-item lists
- List-shaped lines inside fenced code blocks
- Items at different indent levels (different list groups)

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` if any inconsistent list is found, `0` otherwise.

## Verify against the worked example

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff and exit `0` from `diff` (the script itself exits `1`
because the worked example contains intentional findings).

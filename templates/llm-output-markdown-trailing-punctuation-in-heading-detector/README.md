# llm-output-markdown-trailing-punctuation-in-heading-detector

Detect ATX and setext headings that end with disallowed trailing
punctuation. LLMs frequently emit headings as fully-formed sentences
("Why this matters." or "Conclusion:") instead of stripping the terminal
punctuation, which produces awkward table-of-contents entries and
trips markdownlint MD026.

## What it flags

Any heading whose trimmed text ends with one of:

```
. , ; : ! ?
```

Both styles are checked:

- **ATX headings**: `# ...` through `###### ...`, with optional
  trailing-hash closer (`# Heading ##`) — the closer is stripped before
  the punctuation check.
- **Setext headings**: a non-empty line followed by an underline of `=`
  (h1) or `-` (h2).

## What it does not flag

- Headings ending in any other character (letters, digits, `*`, `)`,
  closing brackets, etc.).
- Lines that look like headings but live inside ` ``` ` or `~~~`
  fenced code blocks.
- Setext "headings" whose title line is itself a list item, blockquote,
  pipe-table row, or another ATX heading (those aren't real setext
  headings).

## Notes

- The colon `:` is included by default because that matches markdownlint
  MD026's default `punctuation` list of `.,;:!?`.
- Question marks in FAQ-style headings ("Are we done?") are still
  flagged. If you want question-form headings, suppress this rule for
  those files or rephrase to a noun phrase.

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` if any heading ends with disallowed punctuation, `0`
otherwise.

## Verify against the worked example

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff. The script itself exits `1` because the worked
example contains seven intentional findings (five ATX, two setext); the
clean ATX heading, the clean setext heading, the closing ATX heading,
and the two heading-shaped lines inside the fenced code block are all
correctly skipped.

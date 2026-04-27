# Bad sample — headings without trailing blank lines

# Introduction
This paragraph starts immediately after the H1, with no blank line. Bad.

## Setup
Run the installer and follow the prompts. Also bad — paragraph touches H2.

### Notes
- list item that touches the H3 above. Bad.

#### Edge case
> a blockquote touching an H4. Bad.

##### Final section
```
code block right after H5 — also bad
```

## Consecutive headings — these are fine
### Even nested
#### Like this
Body text after the deepest heading. Bad: H4 touches paragraph.

## Trailing heading is fine on its own

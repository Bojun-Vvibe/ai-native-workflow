# llm-output-markdown-blockquote-marker-spacing-inconsistent-detector

Detects when blockquote `>` markers within a single Markdown document use
inconsistent post-marker spacing (e.g. mixing `> foo`, `>foo`, and `>  foo`).

## Why this matters for LLM outputs

CommonMark accepts all three spacings, so the file *renders* fine. But the
mix is a strong tell that:

- The LLM stitched together fragments from different training sources.
- A previous edit pass partially rewrote the file but not consistently.
- A streaming/repair loop dropped or doubled a space.

Inconsistent blockquote spacing also breaks naive post-processors that strip
the prefix with a fixed regex like `^> ?` vs `^>\s*`.

## What it does

- Streams the input file line-by-line.
- Skips fenced code blocks (` ``` ` and `~~~`).
- For each blockquote line, classifies the *innermost* `>` marker's trailing
  spacing as one of:
  - `none` — `>foo`
  - `one`  — `> foo` (canonical CommonMark)
  - `many` — `>  foo` or more
  - `empty` — `>` alone or `> ` (blank quote line; ignored from the vote)
- If more than one of `{none, one, many}` is observed in the file, picks a
  dominant style (most frequent; ties broken `one > none > many`) and flags
  every line that disagrees.
- Exit code: `1` if any inconsistency, else `0`.

## Run

```
python3 detect.py path/to/file.md
python3 detect.py examples/bad.md   # exits 1
python3 detect.py examples/good.md  # exits 0
```

Stdlib only, Python 3.8+.

## Verified output

Against `examples/bad.md` (exit `1`, 5 findings, dominant=`one`):

```
examples/bad.md:8:1: blockquote-marker-spacing-inconsistent (observed=none, dominant=one)
examples/bad.md:9:1: blockquote-marker-spacing-inconsistent (observed=none, dominant=one)
examples/bad.md:13:1: blockquote-marker-spacing-inconsistent (observed=many, dominant=one)
examples/bad.md:15:1: blockquote-marker-spacing-inconsistent (observed=none, dominant=one)
examples/bad.md:20:1: blockquote-marker-spacing-inconsistent (observed=none, dominant=one)
```

Against `examples/good.md` (exit `0`, no findings, no output).

## Limitations

- Single-file scope: each file is judged in isolation. Cross-file consistency
  is out of scope.
- Only the *innermost* nested marker's spacing is classified — the spacing
  between `>` characters in `> >` vs `>>` is intentionally not flagged here.
- A file with only one style (even if it's `none` or `many`) is considered
  consistent. If you want to enforce `one` everywhere, post-process the
  dominant value.
- Lazy continuation lines (lines that belong to a blockquote but omit the
  `>`) are not tracked; they are not blockquote-marker lines.

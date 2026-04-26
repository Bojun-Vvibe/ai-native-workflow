# `llm-output-inline-code-backtick-balance-detector`

Pure-stdlib detector for unbalanced inline-code backticks in an
LLM Markdown / prose output blob.

## The bug class

A model that emits `` `foo `` and forgets the closing backtick
turns the rest of the paragraph (and sometimes the rest of the
document, depending on the renderer) into one giant inline-code
span. The model itself sees no syntax error — backtick balance is
not enforced by any token-level constraint — but a human reader
sees a wall of monospace where prose was expected.

This detector flags lines where backtick runs cannot be paired by
length. It deliberately ignores lines inside fenced code blocks
(``` … ``` or ~~~ … ~~~), because backticks inside a fence are
content, not Markdown markup.

## Finding kinds

- `odd_total_backtick_run_count` — the line has an odd number of
  backtick runs total. A balanced line always has an even number
  of runs (each opener pairs with a closer of the same length).
  Reported with the column and length of every run on the line so
  the reviewer can see at a glance which one is dangling.

- `unpaired_inline_backtick` — the line has an even total run
  count but at least one run-length appears an odd number of
  times. Example: a line with runs of length `[1, 2, 1, 1]` has
  four runs total (even) but length=1 appears three times
  (unpaired). Reported with the per-length unpaired histogram.

## When to use

- Post-process every LLM Markdown output before rendering or
  shipping, especially long-form answers where the inline-code
  density is high.
- As a CI lint on docs / READMEs that an agent edits.
- As a defensive check before piping LLM output into a Markdown
  renderer that does not visibly distinguish "missing close
  backtick" from "intentional inline code".

## When NOT to use

- On prose that legitimately quotes shell prompts containing
  literal backticks as command substitution markers (`` `date` ``
  is fine, but `` echo `date` `` would correctly flag if the
  closer is missing — but `` `date `` alone in a paragraph would
  still flag).
- On non-Markdown text (plain logs, source code) — the detector
  assumes Markdown semantics for backticks.

## Input

Reads UTF-8 text from stdin or a path argument:

```
python3 detect.py < input.md
python3 detect.py path/to/file.md
```

## Worked example

`example_input.txt`:

```
Line A: balanced `code` here — fine.
Line B: this line opens `foo and never closes the inline span.
Line C: ``literal `tick` inside`` is balanced (runs 2,1,1,2).
Line D: stray triple-tick mid-line ``` is odd-count.

```python
# inside a fenced block — backticks here are CONTENT, not markup.
x = "`unmatched on purpose"
```

Line E: after the fence closes, this `inline` is balanced again.
Line F: but here we have ``unclosed double-tick run.
```

Run:

```
python3 detect.py < example_input.txt
```

Verbatim stdout:

```
FAIL: 3 finding(s).
  L2: odd_total_backtick_run_count run_count=1 runs=[col 25 (len 1)]
  L4: odd_total_backtick_run_count run_count=1 runs=[col 36 (len 3)]
  L12: odd_total_backtick_run_count run_count=1 runs=[col 26 (len 2)]
```

Exit code: `1` (findings present).

Note that lines A, C, and E are not flagged (balanced), and the
backticks inside the fenced ` ```python ` block on lines 7–9 are
correctly ignored — they are code content, not Markdown markup.

## Files

- `detect.py` — pure-stdlib detector
- `example_input.txt` — the worked-example input above
- `README.md` — this file

## Limitations

- The detector is line-scoped: a legitimate inline-code span that
  the model wrote across two lines (`` `foo\nbar` ``) will be
  flagged on both lines as odd-count. In practice, multi-line
  inline-code spans render badly in every Markdown engine and are
  themselves a bug worth flagging.
- Backtick runs are paired by length only, not by position.
  Extremely pathological inputs like `` `a``b`c`` `` (runs 1,2,1,2)
  will pass — every length appears an even number of times — even
  though no real Markdown renderer agrees on how to interpret
  them. Pairing by position would require a small state machine
  and would still not match any single renderer's behavior; the
  length-pair check catches the >99% case (one missing closer)
  with zero state.
- Fenced-block detection only looks at the first non-whitespace
  characters of the line for `` ``` `` or `~~~`. A fence indented
  inside a list item with more than 3 spaces of indent (which
  CommonMark would treat as a code block via indentation, not a
  fence) is not specifically handled — the detector treats it as
  a fence opener if it starts with `` ``` `` after whitespace.
- Empty input returns "OK" with exit 0.

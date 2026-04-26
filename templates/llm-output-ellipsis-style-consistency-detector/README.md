# llm-output-ellipsis-style-consistency-detector

LLMs love to trail off. Sometimes with `...`, sometimes with `…`,
sometimes with `. . .`, and occasionally with `....` (which is just
"three dots followed by a period" but reads as a longer pause).
Mixing these styles in the same document looks sloppy.

This checker scans a piece of text, classifies every ellipsis-like
sequence into one of four styles, picks the dominant one, and reports
every deviation with its line and column.

## Recognized styles

| Style         | Matches                                  |
|---------------|------------------------------------------|
| `unicode`     | the single character `…` (U+2026)        |
| `three_dots`  | exactly three ASCII dots `...`           |
| `spaced_dots` | `. . .` (dots separated by spaces)       |
| `long_dots`   | four or more consecutive ASCII dots      |

## Usage

```sh
python3 check.py example.txt
# or pipe
echo "wait... or wait…" | python3 check.py
```

Stdlib only. Exit code `0` when a single style is used (or no
ellipses are present), `1` otherwise — wire it into a pre-commit hook
or a CI prose-lint job.

## Worked example

`example.txt`:

```
Wait... the model said "Hmm . . . let me think". Then it trailed off…
And then it kept going.... never stopping. Wait...
```

Run:

```sh
$ python3 check.py example.txt
Found 5 ellipsis occurrence(s) across 4 style(s):
  - three_dots: 2
  - spaced_dots: 1
  - unicode: 1
  - long_dots: 1

Dominant style: three_dots
Deviations:
  line 1 col 29: 'spaced_dots' -> '. . .'
  line 1 col 69: 'unicode' -> '…'
  line 2 col 23: 'long_dots' -> '....'
```

The dominant style is `three_dots`, and the three other forms are
flagged with exact positions so the author can normalize them.

## Notes

- "Long dots" (4+) is reported as its own style rather than collapsed
  into `three_dots`, because it is almost always either a typo or a
  deliberate "longer pause" — both worth surfacing.
- The spaced form `. . .` is matched literally with single spaces;
  tab-separated or multi-space variants are intentionally ignored to
  keep false positives down.
- The detector is style-agnostic about which form is "correct" —
  pick the most common one and normalize toward it, or invert the
  policy by editing the dominance rule.

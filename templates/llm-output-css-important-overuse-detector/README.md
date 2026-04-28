# llm-output-css-important-overuse-detector

A small Python 3 stdlib sniffer that flags every `!important` in a CSS /
SCSS / LESS file and reports the per-file density.

## Why it matters for LLM-generated output

When an LLM is asked to "make this button blue" or "fix the layout in
this third-party widget", it routinely reaches for `!important`:

```css
.button {
  background: #1a73e8 !important;
  color: white !important;
}
```

This wins the local override but rots the cascade — every future tweak
needs another `!important`, and specificity loses meaning. CSS lint
guides (Google, Airbnb, MDN) all treat `!important` as a smell except in
narrow cases (utility resets, print stylesheets, third-party overrides).

## Rule

For each input file the detector:

1. Reports every line containing `!important` (case-insensitive,
   tolerant of `! important` with whitespace), including the trimmed
   declaration text.
2. Counts declarations (`prop: value;`) outside of comments.
3. Computes density = `!important / declarations * 100`.
4. Marks the file `OVER-THRESHOLD` when density exceeds `--threshold`
   (default 5%).

Comments (`/* ... */` and SCSS `//`) are stripped before counting so a
commented-out `!important` does not inflate the score.

## Limitations

- Heuristic, not a CSS parser. Multi-line declarations split awkwardly
  across line breaks may under-count declarations slightly, biasing the
  density up. For exact analysis use stylelint's
  `declaration-no-important` rule.
- Does not distinguish "legitimate" uses (utility classes, third-party
  overrides) from sloppy ones — that's a human review decision.

## Usage

```
python3 detector.py [--threshold N] <file.css> [<file.css> ...]
```

Exit code is the total count of `!important` occurrences (capped 255).

## Worked example

```
$ python3 detector.py examples/bad.css
examples/bad.css:3: !important: background: #1a73e8 !important;
examples/bad.css:4: !important: color: white !important;
examples/bad.css:6: !important: border-radius: 4px !important;
examples/bad.css:10: !important: border: 1px solid red !important;
examples/bad.css:11: !important: font-weight: bold !IMPORTANT;
examples/bad.css:15: !important: position: fixed !important;
examples/bad.css:16: !important: inset: 0 ! important; /* spaced variant still flagged */
examples/bad.css: 7 !important / 8 decls (87.5%) OVER-THRESHOLD
findings: 7

$ python3 detector.py examples/good.css
examples/good.css: 0 !important / 8 decls (0.0%)
findings: 0
```

## Files

- `detector.py` — the sniffer.
- `examples/bad.css` — 7 `!important` occurrences across 4 selectors,
  including the case-insensitive (`!IMPORTANT`) and whitespace-tolerant
  (`! important`) variants.
- `examples/good.css` — same selectors and properties, no `!important`.

# `llm-output-markdown-setext-vs-atx-heading-mix-detector`

Pure-stdlib detector for the LLM markdown failure mode where a single
document mixes **ATX-style** headings (`# H1`, `## H2`) with
**Setext-style** headings (text underlined by `===` for H1 or `---`
for H2) at the same rank. Both styles are valid CommonMark, but
mixing them within one document:

- breaks `markdownlint` MD003 (heading-style),
- confuses TOC generators that key off one style,
- makes the raw markdown un-greppable for "all H2s in this doc"
  (`grep '^## '` misses the Setext half),
- produces noisy diffs the moment any auto-formatter (Prettier with
  the markdown plugin, `mdformat`) gets pointed at the file and
  rewrites the minority style.

This is **complementary**, not duplicative, to:

- [`llm-output-setext-heading-underline-length-validator`](../llm-output-setext-heading-underline-length-validator/) —
  validates the underline length of Setext headings; does not flag
  style-mix.
- [`llm-output-markdown-heading-skip-level-detector`](../llm-output-markdown-heading-skip-level-detector/) —
  flags `H1 -> H3` rank skips; does not look at style.
- [`llm-output-atx-heading-trailing-hash-detector`](../llm-output-atx-heading-trailing-hash-detector/) —
  flags `## Title ##` style; does not look at Setext at all.

## Finding kinds

Three kinds, sorted by `(line, kind)` for byte-identical re-runs:

- `mixed_heading_style` — at a given rank (1 or 2; Setext doesn't
  support deeper), the document uses **both** ATX and Setext.
  Reported once per minority-style heading at that rank. The note
  field includes the majority style so a repair prompt can be a
  single string interpolation.
- `setext_h1_below_atx_h1` — order-aware bonus: an ATX H1 appeared
  first and a Setext H1 followed (or vice versa). Reported on the
  second-style first occurrence. Useful when the user's intent
  ("H1 should be the first style I introduced") matters more than
  raw majority count.
- `setext_h2_below_atx_h2` — same axis, H2 vs `---`.

A document that uses only one style at every rank emits **nothing**
(exit 0). Documents with no headings emit nothing.

## Out of scope

- Setext underline length validity → sister template above.
- Skipped heading levels → sister template above.
- Trailing-`#` ATX headings → sister template above.
- HTML headings (`<h2>`) — different parser concern.

## Usage

```sh
python3 detector.py path/to/file.md      # exit 1 on any finding
cat file.md | python3 detector.py -      # stdin mode
```

Output is one JSON object per finding line, e.g.

```json
{"kind": "mixed_heading_style", "line": 9, "note": "...", "rank": 2, "style": "setext", "text": "Setext H2 Sneaks In"}
```

JSON keys are sorted alphabetically so the stream is diff-stable.

## Worked example

`examples/good.md` is a fully ATX document. `examples/bad.md` mixes
an ATX H1 with a trailing Setext H1, and a stretch of ATX H2s with a
Setext H2 in the middle. `examples/expected-output.txt` is the byte
that `python3 detector.py examples/bad.md` produces; `good.md` exits
0 with no output.

```sh
$ python3 detector.py examples/good.md ; echo $?
0
$ python3 detector.py examples/bad.md ; echo $?
{"kind": "mixed_heading_style", "line": 9, ...}
{"kind": "setext_h2_below_atx_h2", "line": 9, ...}
{"kind": "mixed_heading_style", "line": 18, ...}
{"kind": "setext_h1_below_atx_h1", "line": 18, ...}
1
```

## When to wire this in

- **Pre-commit gate** on LLM-drafted README/CHANGELOG when the
  project pins `markdownlint` MD003 — catch the mix at edit time so
  the linter never has to run.
- **Review-loop step** for any agent that generates long-form
  technical writing (architecture docs, runbooks). Mixed heading
  styles are a strong tell that the model concatenated two
  half-completions with different style choices.
- **Diff-noise prevention** in repos where the markdown is also
  consumed by a non-tolerant renderer (Sphinx with
  `myst-parser`, certain wiki engines) that only honors one style.

# llm-output-markdown-heading-level-skip-detector

Pure stdlib detector that scans a markdown document produced by an
LLM for heading-level structural smells. The failure mode it catches:
the model writes a doc that *looks* tidy in a rendered preview but
its heading tree is broken — `##` jumps straight to `####`, the doc
opens at `###` with no `#` parent, two consecutive `#` headings
appear with no body between them, the same heading text repeats at
the same level (anchor collisions in GitHub / GitLab / most static
site generators), or a heading line is empty.

These bugs degrade screen-reader navigation, break TOC generation,
poison downstream chunkers that key on heading depth, and confuse
RAG retrievers that use the heading path as the document ID.

## Why a separate template

Existing siblings cover adjacent concerns:

- `llm-output-fence-extractor` — pulls fenced code blocks out of an
  LLM response. This template is fence-aware in the *opposite*
  direction: it walks past fences without parsing their contents,
  so a `# this is a Python comment` inside a fence is correctly
  ignored as a heading.
- `llm-output-citation-bracket-balance-validator`,
  `llm-output-quotation-mark-balance-validator` — character-level
  balance checks. This template is structural — it cares about the
  H1→H2→H3 tree, not individual characters.
- `llm-output-list-count-mismatch-detector` — list-level structural
  check. Same family of "the doc looks fine until it doesn't,"
  different surface.
- `prompt-section-order-canonicalizer` — operates on the *prompt*
  (input) side. This operates on the *output* side.

## Findings

Deterministic order: `(kind, line_no, detail)` — two runs over the
same input produce byte-identical output (cron-friendly diffing).

| kind | what it catches |
|---|---|
| `level_skip` | a heading jumps more than one level deeper than the previous heading (e.g. `##` → `####`) |
| `no_root` | the very first heading is not `H1` (the doc has no root) |
| `empty_heading` | a heading line has no text after the `#`s (e.g. `## ` or `## ##`) |
| `adjacent_headings` | two headings appear back-to-back with no body content (text, list, fenced block) between them |
| `duplicate_anchor` | two headings at the same level produce the same GitHub-style slug — anchor links collide |
| `trailing_hashes` | a heading uses ATX-closing form (`## Title ##`) — style smell, not a structural break |

`ok` is `False` iff any finding fires.

## Design choices

- **ATX style only.** `#`-prefixed headings. Setext (`===` / `---`
  underlined) is intentionally out of scope — modern LLM output is
  essentially 100% ATX, and supporting both doubles the parser
  surface for marginal gain.
- **Fence-aware.** Lines inside ` ``` ` or `~~~` fenced code blocks
  are NOT parsed as headings. Without this, every Python comment
  and shell prompt would be flagged. Case 07 in the worked example
  proves this.
- **GitHub-style slugs.** `_slugify` lowercases, drops punctuation,
  and replaces spaces / underscores with single dashes — the same
  rule GitHub, GitLab, and most static site generators apply when
  generating heading anchors. Two headings that *render* differently
  but slugify identically still collide on `#anchor` links, which
  is the actual bug.
- **Adjacent-headings only fires when there is genuinely no body.**
  A blank line between two headings is not "body." A list item, a
  paragraph, or a fenced block between them is body and clears the
  flag. This is why case 01 has `# Title` immediately followed (with
  one blank) by `Intro paragraph.` and does *not* fire; case 05's
  `# Title` → blank → `## First` → `## Second` does.
- **Per-level anchor scoping.** Two `## Notes` headings collide; a
  `## Notes` and a `### Notes` do not — anchor namespaces are
  per-level in most renderers.
- **CommonMark-correct heading parser.** The leading `#` run must
  be 1–6 chars. After the `#`s there must be a space or EOL.
  More than 3 leading spaces of indent disqualifies the line (it
  becomes a code block in CommonMark).
- **Pure function.** No I/O, no clocks, no transport. The checker
  takes a string and returns a `HeadingReport`.
- **Stdlib only.** `dataclasses`, `json`. No `re`, no third-party
  markdown parser.

## Composition

- `llm-output-fence-extractor` — when the doc has both fenced code
  *and* heading structure to audit, run the fence extractor first
  to lift out code, then run this on the prose. (This template
  walks fences itself, so for most cases you don't need to.)
- `prompt-template-versioner` — version the system prompt that
  produces the markdown. When this validator starts firing on a
  previously-clean prompt, the version diff is the smoking gun.
- `structured-error-taxonomy` — `level_skip`, `no_root`,
  `empty_heading`, `adjacent_headings`, `trailing_hashes` →
  `attribution=model` (regenerate / repair); `duplicate_anchor`
  → `attribution=model` *or* `attribution=user` if the prompt
  asked for a list of items with naturally-repeating section names
  (in which case widen the slug rule, don't blame the model).

## Worked example

Run `python3 example.py` from this directory. Seven cases — one
clean tree plus one per finding family plus a fence-aware
sanity-check. The output below is captured verbatim from a real
run.

```
# llm-output-markdown-heading-level-skip-detector — worked example

## case 01_clean
input_lines: 15
{
  "findings": [],
  "headings": [
    {
      "anchor": "title",
      "level": 1,
      "line_no": 1,
      "text": "Title"
    },
    {
      "anchor": "section-a",
      "level": 2,
      "line_no": 5,
      "text": "Section A"
    },
    {
      "anchor": "subsection",
      "level": 3,
      "line_no": 9,
      "text": "Subsection"
    },
    {
      "anchor": "section-b",
      "level": 2,
      "line_no": 13,
      "text": "Section B"
    }
  ],
  "ok": true
}

## case 02_level_skip
input_lines: 11
{
  "findings": [
    {
      "detail": "jumped from H2 to H4 (skipped 1)",
      "kind": "level_skip",
      "line_no": 9
    }
  ],
  "headings": [
    {
      "anchor": "title",
      "level": 1,
      "line_no": 1,
      "text": "Title"
    },
    {
      "anchor": "section",
      "level": 2,
      "line_no": 5,
      "text": "Section"
    },
    {
      "anchor": "way-too-deep",
      "level": 4,
      "line_no": 9,
      "text": "Way too deep"
    }
  ],
  "ok": false
}

## case 03_no_root
input_lines: 7
{
  "findings": [
    {
      "detail": "document opens at H2 with no H1 ancestor",
      "kind": "no_root",
      "line_no": 1
    }
  ],
  "headings": [
    {
      "anchor": "subsection-without-parent",
      "level": 2,
      "line_no": 1,
      "text": "Subsection without parent"
    },
    {
      "anchor": "deeper",
      "level": 3,
      "line_no": 5,
      "text": "Deeper"
    }
  ],
  "ok": false
}

## case 04_empty_and_trailing
input_lines: 11
{
  "findings": [
    {
      "detail": "H2 heading has no text",
      "kind": "empty_heading",
      "line_no": 5
    },
    {
      "detail": "H3 heading uses ATX-closing '#' run",
      "kind": "trailing_hashes",
      "line_no": 9
    }
  ],
  "headings": [
    {
      "anchor": "title",
      "level": 1,
      "line_no": 1,
      "text": "Title"
    },
    {
      "anchor": "",
      "level": 2,
      "line_no": 5,
      "text": ""
    },
    {
      "anchor": "closed-style",
      "level": 3,
      "line_no": 9,
      "text": "Closed Style"
    }
  ],
  "ok": false
}

## case 05_adjacent_no_body
input_lines: 6
{
  "findings": [
    {
      "detail": "H2 immediately follows previous heading at line 1 with no body",
      "kind": "adjacent_headings",
      "line_no": 3
    },
    {
      "detail": "H2 immediately follows previous heading at line 3 with no body",
      "kind": "adjacent_headings",
      "line_no": 4
    }
  ],
  "headings": [
    {
      "anchor": "title",
      "level": 1,
      "line_no": 1,
      "text": "Title"
    },
    {
      "anchor": "first",
      "level": 2,
      "line_no": 3,
      "text": "First"
    },
    {
      "anchor": "second",
      "level": 2,
      "line_no": 4,
      "text": "Second"
    }
  ],
  "ok": false
}

## case 06_duplicate_anchor
input_lines: 11
{
  "findings": [
    {
      "detail": "H2 anchor 'notes' duplicates line 5",
      "kind": "duplicate_anchor",
      "line_no": 9
    }
  ],
  "headings": [
    {
      "anchor": "doc",
      "level": 1,
      "line_no": 1,
      "text": "Doc"
    },
    {
      "anchor": "notes",
      "level": 2,
      "line_no": 5,
      "text": "Notes"
    },
    {
      "anchor": "notes",
      "level": 2,
      "line_no": 9,
      "text": "Notes"
    }
  ],
  "ok": false
}

## case 07_fence_aware
input_lines: 10
{
  "findings": [],
  "headings": [
    {
      "anchor": "title",
      "level": 1,
      "line_no": 1,
      "text": "Title"
    },
    {
      "anchor": "real-section",
      "level": 2,
      "line_no": 8,
      "text": "Real Section"
    }
  ],
  "ok": true
}
```

Read across the cases: 01 is the only clean tree. 02 catches the
classic "agent skipped a level because it forgot it was already two
levels deep." 03 catches doc fragments — missions that asked for a
section and got handed a top-level subdocument with no `H1`. 04
folds two style smells (empty heading, ATX closing) into one case.
05 is the back-to-back-headings smell that breaks TOCs because the
intermediate heading has no anchor target text under it. 06 is the
collision case: both `## Notes` headings render fine, but the
second `#notes` link silently jumps to the first. 07 is the
fence-aware sanity check — heading-looking lines inside a Python
fenced block must NOT be parsed as headings, and they aren't.

The output is byte-identical between runs — `_CASES` is a fixed
list, the checker is a pure function, and findings are sorted by
`(kind, line_no, detail)` before serialisation.

## Files

- `example.py` — the checker + the runnable demo.
- `README.md` — this file.

No external dependencies. Tested on Python 3.9+.

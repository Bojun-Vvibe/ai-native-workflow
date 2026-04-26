# llm-output-markdown-heading-skip-level-detector

Pure-stdlib detector for ATX-heading level skips in LLM-generated
markdown. Catches the silent-corruption class where the document goes
from `#` straight to `###` (skipping `##`), or starts with `## Foo`
when the surrounding tooling expects a single h1 root. The prose reads
fluently — the model "knew" it wanted a sub-sub-section — but it never
emitted the parent heading, which silently breaks downstream TOC
generators, accessibility tooling, RAG section-chunkers, and any
serialiser that reconstructs a tree from heading depth.

## What it catches

| kind | what it catches |
|---|---|
| `leading_skip` | the very first heading is deeper than h1 (e.g. document opens with `## Foo`) |
| `skip_level` | a forward jump greater than `max_skip` (default 1), e.g. h1 → h3, h2 → h5 |

Descending jumps are always allowed (`### C` → `# D` is normal —
returning to a top-level section). `max_skip` is configurable so that
codebases that legitimately use h1→h3 in subdocuments can opt out.

## Why a separate template

Adjacent siblings cover different layers:

- `llm-output-markdown-ordered-list-numbering-monotonicity-validator`
  — same family (markdown structural discipline) but for list
  numbering, not heading depth.
- `llm-output-markdown-blank-line-around-fenced-code-block-validator`
  — markdown surface, blank-line discipline. Different bug class.
- generic outline / TOC validators — usually require a parsed AST and
  external dependencies. This template is one forward scan, no regex,
  stdlib only, and is safe to run on partial / streamed output.

## Design choices

- **ATX only.** `# `…`###### ` style. Setext underlines (`===` / `---`)
  intentionally out of scope; a separate template can handle them.
  Mixing the two surfaces in one detector blurs the bug taxonomy.
- **Fenced code blocks are stripped.** Lines inside ``` … ``` (or
  `~~~ … ~~~`) are ignored so a `# comment` inside a Python sample
  never trips as a heading. The fence parser tracks fence character
  and length so a longer fence can contain a shorter one.
- **CommonMark-shaped parser.** 0–3 leading spaces, 1–6 hashes, then a
  space or end-of-line. `##bold` is *not* a heading. Trailing closing
  hashes (`## Foo ##`) are stripped.
- **Configurable tolerance.** `max_skip=1` is strict (the
  accessibility default). `max_skip=2` permits h1→h3 for documents
  that use h1 only as a title.
- **Deterministic output.** Findings sorted by `(kind, line, detail)`.
  Two runs over the same input produce byte-identical JSON.
- **Eager refusal on bad input.** Non-`str` markdown or non-positive
  `max_skip` raises `HeadingSkipDetectionError` immediately.
- **Pure function.** No I/O, no clocks, no transport.
- **Stdlib only.** `dataclasses`, `json`. No `re`.

## Composition

- Run *before* any TOC / outline generator that assumes contiguous
  depth. A `skip_level` finding is the cheapest possible signal that
  the generator's tree will be malformed.
- Run *after* `llm-output-fence-extractor` if you have one — though
  this template already strips fenced code internally, so it is safe
  to run on raw model output.
- Pair with `agent-decision-log-format`: one log line per finding,
  sharing `line` so a reviewer jumps straight to the offending span.

## How to run

```
python3 example.py
```

No arguments. No external dependencies. Tested on Python 3.9+.

## Worked example

Seven cases — clean, h1→h3 skip, leading h2, multiple skips, valid
descents, fenced-code-aware, and `max_skip=2` opt-in. Output below
captured verbatim from `python3 example.py`.

```
# llm-output-markdown-heading-skip-level-detector — worked example

## case 01_clean
max_skip=1
markdown:
  | # Title
  | 
  | Intro.
  | 
  | ## Section
  | 
  | Body.
  | 
  | ### Subsection
  | 
  | More body.
  | 
  | ## Another
{
  "findings": [],
  "headings": [
    {
      "level": 1,
      "line": 1,
      "text": "Title"
    },
    {
      "level": 2,
      "line": 5,
      "text": "Section"
    },
    {
      "level": 3,
      "line": 9,
      "text": "Subsection"
    },
    {
      "level": 2,
      "line": 13,
      "text": "Another"
    }
  ],
  "ok": true
}

## case 02_h1_to_h3
max_skip=1
markdown:
  | # Title
  | 
  | Intro.
  | 
  | ### Buried subsection — model forgot the ## parent
  | 
  | Body.
{
  "findings": [
    {
      "detail": "h1 -> h3 (jump of 2, max_skip=1)",
      "kind": "skip_level",
      "line": 5
    }
  ],
  "headings": [
    {
      "level": 1,
      "line": 1,
      "text": "Title"
    },
    {
      "level": 3,
      "line": 5,
      "text": "Buried subsection \u2014 model forgot the ## parent"
    }
  ],
  "ok": false
}

## case 03_leading_h2
max_skip=1
markdown:
  | ## Starts deep
  | 
  | Body.
  | 
  | ### Child
{
  "findings": [
    {
      "detail": "document starts at h2, expected h1",
      "kind": "leading_skip",
      "line": 1
    }
  ],
  "headings": [
    {
      "level": 2,
      "line": 1,
      "text": "Starts deep"
    },
    {
      "level": 3,
      "line": 5,
      "text": "Child"
    }
  ],
  "ok": false
}

## case 04_multiple_skips
max_skip=1
markdown:
  | # Top
  | 
  | ### Skipped once
  | 
  | Body.
  | 
  | ###### Skipped again
{
  "findings": [
    {
      "detail": "h1 -> h3 (jump of 2, max_skip=1)",
      "kind": "skip_level",
      "line": 3
    },
    {
      "detail": "h3 -> h6 (jump of 3, max_skip=1)",
      "kind": "skip_level",
      "line": 7
    }
  ],
  "headings": [
    {
      "level": 1,
      "line": 1,
      "text": "Top"
    },
    {
      "level": 3,
      "line": 3,
      "text": "Skipped once"
    },
    {
      "level": 6,
      "line": 7,
      "text": "Skipped again"
    }
  ],
  "ok": false
}

## case 05_descents_are_fine
max_skip=1
markdown:
  | # A
  | 
  | ## B
  | 
  | ### C
  | 
  | # D
  | 
  | ## E
{
  "findings": [],
  "headings": [
    {
      "level": 1,
      "line": 1,
      "text": "A"
    },
    {
      "level": 2,
      "line": 3,
      "text": "B"
    },
    {
      "level": 3,
      "line": 5,
      "text": "C"
    },
    {
      "level": 1,
      "line": 7,
      "text": "D"
    },
    {
      "level": 2,
      "line": 9,
      "text": "E"
    }
  ],
  "ok": true
}

## case 06_inside_fenced_code_ignored
max_skip=1
markdown:
  | # Real heading
  | 
  | ```
  | # not a heading
  | ### also not
  | ```
  | 
  | ## Sibling
{
  "findings": [],
  "headings": [
    {
      "level": 1,
      "line": 1,
      "text": "Real heading"
    },
    {
      "level": 2,
      "line": 8,
      "text": "Sibling"
    }
  ],
  "ok": true
}

## case 07_max_skip_2_allows_h1_to_h3
max_skip=2
markdown:
  | # Top
  | 
  | ### Two-level jump
  | 
  | #### Child
{
  "findings": [],
  "headings": [
    {
      "level": 1,
      "line": 1,
      "text": "Top"
    },
    {
      "level": 3,
      "line": 3,
      "text": "Two-level jump"
    },
    {
      "level": 4,
      "line": 5,
      "text": "Child"
    }
  ],
  "ok": true
}
```

## Files

- `example.py` — the detector + the runnable demo.
- `README.md` — this file.

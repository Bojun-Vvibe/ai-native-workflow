# llm-output-markdown-link-fragment-anchor-undefined-detector

## Problem

LLM-authored markdown frequently contains intra-document links like
`[Setup](#setup)` or `[Troubleshooting](#trouble-shooting)` whose
`#anchor` does not actually correspond to any heading in the same
document. The model invents plausible slugs based on what *would*
typically be a section name, even when the real heading is missing,
named slightly differently, or has been renamed in a later draft.

These broken intra-document anchors render as clickable text but
silently jump to the top of the page (or nowhere). They almost never
get caught by reviewers because the link text reads correctly.

## Use case

- Run as a markdown lint over an LLM-produced document before
  rendering or publishing.
- Run in CI against a docs tree to catch drift after section renames.
- Pair with the existing `llm-output-markdown-heading-skip-level-detector`
  / `llm-output-markdown-heading-level-skip-detector` template for a
  fuller heading-graph audit.

## What it detects

For each markdown link `[text](href)` in the document where `href`
starts with `#`:

- `undefined_anchor` — the slug after `#` does not match any heading
  slug in the document.
- `empty_fragment` — the href is just `#`.

External links (`https://...`, `./other.md`, etc.) are ignored. Links
inside fenced code blocks (``` ``` ``` or `~~~`) are ignored, and
headings inside fenced code blocks do NOT contribute slugs.

### Slug rules (GitHub-flavored)

For each ATX heading `## Some Heading!`:

1. Strip markdown emphasis markers (`` ` * _ ~ ``).
2. Lowercase, trim whitespace.
3. Collapse internal whitespace runs to a single `-`.
4. Drop characters that are not `[a-z0-9_-]`.
5. If the same slug appears multiple times in the doc, the second is
   `slug-1`, the third is `slug-2`, and so on.

## How to run

```
python3 detector.py <path-to-markdown-file>
```

Exit code `0` means every intra-document anchor resolves. Exit code
`1` means at least one issue was reported.

## Worked example

Input (`worked-example/sample.md`) intentionally contains:

- A correct anchor: `#overview`, `#setup`, `#setup-1` (duplicate
  heading), and `#faq`.
- A misspelled anchor: `#trouble-shooting` (real heading slugs to
  `troubleshooting`).
- An expanded-form anchor that does not match: `#frequently-asked-questions`
  (real heading is `## FAQ`, slug `faq`).
- A made-up anchor: `#glossary` (no such heading exists).
- An empty fragment: `[bad fragment](#)`.
- An external link with a fragment that should be ignored.
- A fenced code block whose fake heading and fake link must be ignored.

Run:

```
$ python3 detector.py worked-example/sample.md
```

Actual output:

```json
{
  "path": "worked-example/sample.md",
  "heading_count": 6,
  "issue_count": 4,
  "headings": [
    {
      "line": 1,
      "slug": "project-notes"
    },
    {
      "line": 8,
      "slug": "overview"
    },
    {
      "line": 12,
      "slug": "setup"
    },
    {
      "line": 16,
      "slug": "setup-1"
    },
    {
      "line": 21,
      "slug": "troubleshooting"
    },
    {
      "line": 26,
      "slug": "faq"
    }
  ],
  "issues": [
    {
      "kind": "undefined_anchor",
      "line": 3,
      "col": 49,
      "href": "#trouble-shooting",
      "text": "Troubleshooting",
      "hint": "No heading in this document slugs to that anchor."
    },
    {
      "kind": "undefined_anchor",
      "line": 4,
      "col": 12,
      "href": "#frequently-asked-questions",
      "text": "the FAQ",
      "hint": "No heading in this document slugs to that anchor."
    },
    {
      "kind": "undefined_anchor",
      "line": 4,
      "col": 55,
      "href": "#glossary",
      "text": "Glossary",
      "hint": "No heading in this document slugs to that anchor."
    },
    {
      "kind": "empty_fragment",
      "line": 6,
      "col": 37,
      "href": "#",
      "text": "bad fragment",
      "hint": "The fragment is empty (just '#')."
    }
  ]
}
```

Exit code: `1`.

Note: `#setup-1` correctly resolves because the duplicate `## Setup`
heading triggers the `slug-N` counter.

## Limitations

- ATX headings only (`# H1` … `###### H6`). Setext headings (`===` /
  `---` underlines) are not parsed.
- Slug rules follow the common GitHub flavor; renderers vary
  (e.g. `kramdown`, `markdown-it` with `markdown-it-anchor`,
  Bitbucket). For exotic renderers, fork `slugify()`.
- HTML anchors injected as `<a name="...">` or `<a id="...">` are not
  considered. Add an HTML-anchor scan if your docs rely on them.
- Reference-style links (`[text][ref]` + `[ref]: #anchor`) are not
  handled in this minimal version.
- Only stdlib used (`re`, `argparse`, `json`).

# llm-output-markdown-heading-id-attribute-duplicate-detector

Detects duplicate explicit heading id attributes in Markdown — e.g.
two headings both ending in `{#overview}`.

## Why this matters

Pandoc, kramdown, MkDocs, Hugo, Jekyll (with kramdown), and many
other Markdown engines support an explicit heading-id syntax:

```markdown
## Heading text {#custom-id}
```

The id becomes the URL fragment for in-page anchor links. If the same
id appears on two headings in one document:

* in-page links to `#custom-id` resolve non-deterministically (browsers
  usually pick the first match, but link-checkers may flag the second
  as broken)
* generated tables of contents collapse the two entries into one
* downstream tools that index headings by id (search, breadcrumbs,
  cross-references) silently lose one of the entries

LLMs reuse boilerplate slugs (`#overview`, `#summary`, `#example`,
`#api`) across regenerated sections, so this defect appears regularly
in machine-assembled long-form Markdown.

## What it detects

Each ATX heading line of the form

```
^[#]{1,6} <text> {#<id>}$
```

contributes its id to a seen-set. Every subsequent occurrence of an
already-seen id is reported with the line number of the first
definition.

Setext headings (`====` / `----` underline style) cannot carry id
attributes in the standard syntax and are intentionally not scanned.

## Code-fence awareness

The scanner tracks fenced-code-block state. Heading-shaped lines
inside an open ` ``` ` or `~~~` block are skipped, so a tutorial that
quotes the duplicate-id syntax as a code sample does not produce
false positives.

## How to run

```bash
python3 detect.py example/bad.md
```

Exit codes:

* `0` — clean
* `1` — one or more findings printed to stdout
* `2` — usage / IO error

## CI usage

```yaml
- name: Lint markdown for duplicate heading ids
  run: |
    find docs -name '*.md' -print0 | \
      xargs -0 -n1 python3 templates/llm-output-markdown-heading-id-attribute-duplicate-detector/detect.py
```

## Worked example

`example/bad.md` defines `#overview` twice and `#api` three times,
plus contains a fenced code block whose content shows the very same
duplicate-id pattern as documentation. Running the detector produces
`example/expected-output.txt` verbatim (3 findings) and exits with
status `1` — the in-fence occurrences are NOT counted.

`example/good.md` exercises the same surface with all-unique ids and
the same fenced code block. The detector exits `0` with no output.

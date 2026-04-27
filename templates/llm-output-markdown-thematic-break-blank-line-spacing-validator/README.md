# llm-output-markdown-thematic-break-blank-line-spacing-validator

## What this catches

LLM-generated markdown frequently emits thematic breaks (horizontal rules:
`---`, `***`, `___`) without the blank lines required around them by
CommonMark. When a `---` line is touching surrounding paragraph text it is
either reinterpreted as a Setext heading underline (turning the previous
paragraph into an `<h2>`) or silently rendered as plain text. Either way the
intended visual divider is lost.

This validator scans a markdown file and flags every thematic-break line that
is not preceded AND followed by a blank line (or the document edge).

## Why it matters for AI-native workflows

LLMs that stream long-form structured answers (briefings, multi-section
reports, RFC drafts) lean on thematic breaks to separate sections. When the
model omits the surrounding blank lines, downstream renderers (GitHub, Slack
unfurl, MkDocs, Pandoc) silently produce different DOMs from what the model
"thinks" it wrote, which then poisons any downstream evaluation that compares
rendered HTML to expected structure.

## Files

- `detector.py` — the validator. Exit code `0` clean, `1` if findings.
- `bad.md` — worked example that MUST fail (thematic breaks with no
  surrounding blank lines + a thematic break that gets eaten as a Setext
  heading underline).
- `good.md` — worked example that MUST pass.

## Usage

```
python3 detector.py path/to/file.md
```

Output on findings is one line per offence:

```
<path>:<line>: thematic break missing blank line <before|after>
```

## Verified runnable

```
$ python3 detector.py good.md ; echo "exit=$?"
exit=0
$ python3 detector.py bad.md ; echo "exit=$?"
bad.md:4: thematic break missing blank line before
bad.md:4: thematic break missing blank line after
bad.md:8: thematic break missing blank line before
bad.md:8: thematic break missing blank line after
bad.md:13: thematic break missing blank line after
exit=1
```

## Rule shape

A line is a thematic break iff, after stripping up to 3 leading spaces, it
consists of 3+ of the same marker (`-`, `*`, or `_`) optionally separated by
spaces/tabs, with nothing else on the line. The line BEFORE and the line
AFTER must each be either absent (BOF/EOF) or blank (only whitespace).

# llm-output-em-dash-hyphen-usage-consistency-detector

Detect mixed dash conventions in LLM-generated prose.

## Purpose

When an LLM stitches together text from training sources with different
typographic conventions, the output frequently mixes:

- **Em dash** `—` (U+2014) — used as a parenthetical break.
- **En dash** `–` (U+2013) — used for numeric / date ranges.
- **Double hyphen** `--` — ASCII stand-in for em dash.
- **Spaced hyphen** ` - ` — another ASCII stand-in for em dash.

A single document should generally pick *one* convention and stick to it.
This detector flags documents that use two or more.

Inline code spans (`` ` ` ``) and fenced code blocks (` ``` ` / ` ~~~ `)
are stripped before analysis so that legitimate CLI flags like `--verbose`
or `cmd -- --flag` inside code samples don't trigger false positives.

## Inputs

- A markdown or plain-text document, either:
  - As a file path: `python3 check.py path/to/doc.md`
  - Or piped via stdin: `cat doc.md | python3 check.py`

## Outputs

- Per-convention counts on stdout.
- Sample context snippets for em-dash and en-dash hits.
- Exit code `0` if at most one convention is used, `1` if two or more.
- Python 3 stdlib only — no external dependencies.

## When to use

- CI gate on long-form generated content where typographic consistency
  matters (publishing pipelines, doc generators, marketing copy).
- Pre-merge check on AI-drafted READMEs and design notes.
- Spot-audit of a corpus of generated articles before bulk publishing.

## Worked example

Fixture (`/tmp/dash_fixture.txt`):

```
# Notes

The model — quite confidently — claimed the range was 10–20 units.
But later the same paragraph says the figure was wrong -- and that the
real range is 5 - 15 instead. Use `--flag` to override (this is code).

```
run -- --verbose --count 3
```
```

This text intentionally mixes all four conventions in the prose, while
also including `--flag` inline-code and a fenced block with double
hyphens that should be ignored.

Command:

```
python3 templates/llm-output-em-dash-hyphen-usage-consistency-detector/check.py /tmp/dash_fixture.txt
```

Actual output:

```
em_dash      (—) count: 2
en_dash      (–) count: 1
double_hyphen (--)  count: 1
spaced_hyphen ( - ) count: 1
distinct conventions used: ['double_hyphen', 'em_dash', 'en_dash', 'spaced_hyphen']
status: FAIL (mixed dash conventions: 4)
  em_dash examples:
    ...# Notes  The model — quite confidently —...
    ...— quite confidently — claimed the range w...
  en_dash examples:
    ...med the range was 10–20 units. But later ...
exit=1
```

All four conventions are detected in the prose, while the `--verbose`,
`--count`, and `-- ` tokens inside the fenced code block and inline code
are correctly excluded from the count.

## Limitations

- Treats any non-bracketed `--` outside code as a dash. Long ASCII rules
  (`---`, `----`) are intentionally not counted.
- Does not attempt to *fix* the inconsistency, only to report it.
- Spaced-hyphen detection requires word characters on both sides; bullet
  lines like `- item` are not counted.
- A document that uses em dash exclusively for parentheticals and en dash
  exclusively for ranges is — strictly speaking — mixing two conventions
  and will be flagged. Tune downstream policy accordingly.

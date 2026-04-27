# llm-output-blockquote-attribution-style-detector

## What it detects

Inconsistent or malformed attribution lines inside Markdown blockquotes that
LLMs tend to produce when quoting people. Specifically:

1. Mixed attribution styles within a single document — some quotes use the
   typographic em-dash (`—`), others use a double hyphen (`--`), others use a
   single hyphen (`- `). Pick one and stick with it.
2. Attribution lines that are *not* themselves blockquoted (the dash line
   sits outside the `>` block, breaking visual grouping in most renderers).
3. Attribution lines that use an em-dash but no author follows
   (`> ...\n> —`) — orphan attribution.

## Why it matters

LLMs frequently copy quote formatting from training data inconsistently:
one paragraph uses Chicago-style em-dash attribution, the next uses Markdown
list-style `- Author`. Renderers handle these differently, and reviewers waste
time deciding whether the inconsistency is intentional. Catch it pre-publish.

## Usage

```
python3 detector.py path/to/file.md
```

Exit codes:
- `0` — no findings
- `1` — at least one finding (printed to stdout, one per line)

Stdlib only. No dependencies.

## Rules in detail

A blockquote block is a maximal run of consecutive lines starting with `>`.
Within that block, the *last* non-empty line is examined. If it matches one
of the attribution patterns (`—`, `--`, `- ` followed by text), the dash
style is recorded for the block. After scanning the whole document:

- If two or more distinct dash styles appear, every block using the
  minority style is reported as `mixed-attribution-style`.
- If a non-quoted line immediately following a blockquote starts with a
  dash and looks like an attribution (`— Name`, `-- Name`), it is reported
  as `attribution-outside-blockquote`.
- A blockquote whose last line is just `>` followed by `—` / `--` with no
  author text is reported as `orphan-attribution`.

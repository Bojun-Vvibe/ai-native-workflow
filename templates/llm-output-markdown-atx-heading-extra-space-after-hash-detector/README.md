# llm-output-markdown-atx-heading-extra-space-after-hash-detector

Detect ATX headings with more than one space between the opening hash
run and the heading text, or more than one space before the optional
closing hash run.

LLMs frequently emit `##  Heading` or `###    Heading` — the model
visually padded the heading to align with surrounding tokens, but the
extra spaces are *not* part of the heading text and most renderers
silently eat them. Lint tooling does not: markdownlint MD019 fires on
extra spaces inside an open ATX heading, and MD021 fires on extra
spaces inside a closed one (`## Heading  ##`).

## What it flags

- **`extra_space_after_open`** — more than one space (or tab) between
  the opening `#` run and the first non-space character of the
  heading text. Levels h1 through h6.
- **`extra_space_before_close`** — for "closed" ATX headings such as
  `## Heading  ##`, more than one space between the heading text and
  the trailing hash run. Reported as a separate finding so a heading
  that is bad on both sides produces two distinct lines.

For each finding the line, level, observed space count, and a 50-char
preview of the heading text are printed.

## What it does NOT flag

- ATX headings with exactly one space after the opener (the spec
  requirement).
- Setext headings (`Title\n=====` / `Title\n-----`) — different shape,
  different lint rule.
- Anything inside fenced code blocks (` ``` ` or `~~~`).
- Lines indented by 4+ spaces (those are code blocks per CommonMark).
- Empty headings (`#` with nothing after) — that is a separate finding
  class handled elsewhere.

## Why this matters

- **Diff hygiene**: a heading whose content drifts by an invisible
  whitespace count produces noisy git blames and review diffs.
- **Slug determinism**: heading-anchor generators usually `strip()` the
  text before slugging, but a handful of older renderers fold the
  extra spaces into the slug, producing broken anchors.
- **Lint compatibility**: gives a stdlib-only equivalent of MD019 +
  MD021 for pipelines that cannot install Node-based markdownlint.

## Usage

```
python3 script.py < your-doc.md
```

Exit code `1` on any finding (one line per finding on stdout), `0` on
a clean document.

## Verify against the worked example

```
python3 script.py < worked-example/input.md | diff - worked-example/expected-output.txt
```

Should produce no diff. The script itself exits `1` because the input
contains seven intentional findings:

- three open-ATX headings with 2/3/4 trailing spaces after the opener,
- one closed heading with extra space before the closer,
- one closed heading with three spaces before the closer,
- one closed heading bad on *both* sides (counted twice).

A clean companion file is also provided:

```
python3 script.py < worked-example/clean.md ; echo "exit=$?"
```

Should print `exit=0` with no other output.

## Implementation notes

- Pure Python 3 standard library, no third-party dependencies.
- The ATX matcher allows the spec-permitted 0-3 spaces of leading
  indentation; 4+ spaces is left alone (CommonMark code block).
- Tabs after the hash run count as "spaces" for the purposes of the
  count, matching MD019/MD021 behavior.
- The closed-heading matcher uses a separate, anchored regex over the
  remainder of the heading line so opening and closing findings can
  be reported independently on the same line.

# llm-output-atx-heading-trailing-hash-detector

Detect ATX-style markdown headings that use the optional closing-hash form
(`## Title ##`). CommonMark allows this, but most house styles ban it because
LLMs apply it inconsistently — some headings get the trailing hashes, others
don't, producing visual noise in long documents.

## What it flags

For every heading line of the form:

```
<level-hashes> <title> <trailing-hashes>
```

it reports the line number, heading level, title text, and the trailing-hash
run length. Fenced code blocks are skipped so example markdown inside backtick
fences does not produce false positives.

## What it does not flag

- Open-form headings: `## Title`
- Setext headings (`Title\n=====`)
- Headings inside fenced code blocks
- Inline `#` characters that are not at the end of a heading line

## Usage

```
python3 script.py < your-doc.md
```

Exit code `0` means clean; exit code `1` means at least one heading was
flagged.

## Worked example

Input (`sample-input.txt`):

```
# Intro

This document explains the feature.

## Overview ##

Some text.

### Details

More text.

## Conclusion ###

Wrap up.

```markdown
## Not a real heading ##
```

#### Appendix ####
```

Run:

```
python3 script.py < sample-input.txt
```

Verbatim output:

```
FOUND 3 heading(s) with trailing hashes:
  line 5: level=2 title='Overview' trailing='##'
  line 13: level=2 title='Conclusion' trailing='###'
  line 21: level=4 title='Appendix' trailing='####'
```

Exit code: `1`.

Note that line 19 (`## Not a real heading ##` inside the fenced block) is
correctly ignored.

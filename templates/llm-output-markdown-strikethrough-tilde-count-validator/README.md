# llm-output-markdown-strikethrough-tilde-count-validator

Validates that GFM strikethrough markers in Markdown use exactly two tildes
per side (`~~text~~`) — and flags the malformed variants LLMs love to
emit:

* `~text~`     — single tilde, not strikethrough in GFM
* `~~~text~~~` — three tildes, collides with code-fence syntax
* `~~text~`    — mismatched closing run
* `~text~~`    — mismatched opening run

## Why this matters

GFM strikethrough is one of the most format-fragile Markdown features.
LLMs trained on mixed Markdown dialects (Pandoc, MultiMarkdown, GFM)
hallucinate single-tilde or triple-tilde strikethrough, producing output
that renders as literal tildes or — worse — opens an unintended fenced
code block.

## When to use

* CI gate on Markdown output from a model.
* Spot-check before publishing LLM-drafted release notes / docs.
* Triage during a flaky-strikethrough rendering bug.

## How to run

```
python3 detect.py path/to/file.md
```

Exit codes:

* `0` — clean
* `1` — findings printed to stdout
* `2` — usage error

## What it ignores

* Lines inside fenced code blocks (``` or `~~~`).
* Lines without any tilde character.

## Heuristic

Within each line, tilde runs are paired greedily left-to-right. A pair is
valid only when both sides are exactly 2 tildes. An odd, unpaired trailing
run is reported as `unpaired tilde run`.

This is intentionally a lint-grade heuristic, not a full CommonMark+GFM
parser. False positives on lines that legitimately contain three or more
unrelated tildes (rare in prose) are acceptable; the value is catching the
common LLM failure modes.

## Worked example

```
python3 detect.py example/bad.md
```

See `example/expected-output.txt`.

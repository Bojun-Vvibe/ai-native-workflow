# llm-output-markdown-hard-line-break-trailing-space-detector

Detects Markdown hard-line-break trailing spaces — the "two-or-more spaces
before a newline" pattern that renders as `<br>` — in LLM-generated
Markdown where they are almost always unintended.

## Why this matters

Most LLMs occasionally emit lines that end with two trailing spaces. The
intent is usually nothing — it's a training-data artifact. But CommonMark
turns those invisible spaces into a `<br>` tag, which:

* Breaks diff hygiene (whitespace-only changes flip semantics).
* Pollutes Markdown-to-plaintext conversion (extra `\n`s).
* Causes subtle layout bugs in rendered docs.

Treat this detector as a lint pass before committing LLM-authored Markdown.

## When to use

* CI gate on Markdown files generated or edited by an agent.
* Local pre-commit when you trust your editor more than the model.
* Cleaning up doc PRs from a model that's prone to soft-wrapping.

## How to run

```
python3 detect.py path/to/file.md
```

Exit codes:

* `0` — clean
* `1` — findings printed to stdout
* `2` — usage error (printed to stderr)

## What it ignores

* Lines inside fenced code blocks (``` or `~~~`).
* Blank lines (only whitespace).

## Worked example

```
python3 detect.py example/bad.md
```

See `example/expected-output.txt` for the expected output. The example file
seeds three intentional hard-line-break lines and one fenced-code line that
should NOT be flagged.

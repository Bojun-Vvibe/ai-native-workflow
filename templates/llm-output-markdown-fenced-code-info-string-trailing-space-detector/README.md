# llm-output-markdown-fenced-code-info-string-trailing-space-detector

Detects trailing whitespace (space or tab) on the *info string* of a fenced
code block opener — e.g. ```` ```python␠ ```` instead of ```` ```python ````.

## Why this matters for LLM outputs

CommonMark and most renderers silently trim the info string, so the rendered
page looks fine. But the trailing whitespace is a strong tell that:

- The model emitted the language tag and then a stray space before the newline,
  often because of token-boundary streaming artifacts.
- A repair / rewrite pass appended an attribute (e.g. `python title="x"`) and
  later deleted it without trimming the leftover space.
- The output came from concatenating two model turns where the join landed on
  a space.

It also breaks naive consumers that key off the literal info string
(`info == "python"` checks fail), and confuses some highlighters and
extractors that tokenize on the raw value.

## What it does

- Streams the file line-by-line.
- Tracks fenced code state (` ``` ` and `~~~`, including 4+ char fences).
- For every *opener* with a non-empty info string, checks whether the info
  string ends in space or tab characters before the line break.
- All-whitespace info strings are NOT flagged here (CommonMark treats them as
  empty; that's a different lint).
- Only flags openers; closing fences are out of scope.
- Backtick-fenced openers whose info string contains a backtick are skipped
  per CommonMark.

## Run

```
python3 detect.py path/to/file.md
python3 detect.py examples/bad.md   # exits 1
python3 detect.py examples/good.md  # exits 0
```

Stdlib only, Python 3.8+.

## Verified worked example

Against `examples/bad.md` — exit `1`, **4 findings**:

```
examples/bad.md:5:10: fenced-code-info-string-trailing-space (fence=```, info='python ')
examples/bad.md:11:8: fenced-code-info-string-trailing-space (fence=```, info='json\\t')
examples/bad.md:17:8: fenced-code-info-string-trailing-space (fence=~~~, info='bash  ')
examples/bad.md:29:9: fenced-code-info-string-trailing-space (fence=````, info='diff ')
```

Against `examples/good.md` — exit `0`, **0 findings** (no output).

## When to use

- As a CI lint on LLM-generated docs, READMEs, or chat transcripts that round-
  trip through Markdown.
- As a pre-commit hook on agent-authored markdown to catch repair-pass
  artifacts before review.
- As a one-shot diagnostic when an extractor that keys on the literal info
  string starts mysteriously dropping blocks.

## Limitations

- Single-file scope; no cross-file aggregation.
- Does not flag trailing whitespace on *closing* fences (separate concern).
- Does not normalize / fix; report only. Pair with a fixer that calls
  `info_str.rstrip()` if you want auto-repair.
- Indented code blocks (4-space indent, no fence) are not in scope by
  definition — they have no info string.

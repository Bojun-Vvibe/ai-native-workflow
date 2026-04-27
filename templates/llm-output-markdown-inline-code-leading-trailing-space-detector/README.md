# llm-output-markdown-inline-code-leading-trailing-space-detector

## Intent
Detect inline-code spans in markdown that have **unnecessary** leading or
trailing whitespace inside the backticks, e.g. `` ` foo ` `` or `` `foo  ` ``.

GFM allows exactly one leading and one trailing space *only* when the content
itself starts or ends with a backtick (the
"`` ` `` ` `` ` ``" escape trick). In every other case, surrounding spaces are
unintended noise — usually an LLM artifact when it copied a phrase like
`"the function `foo` is …"` and accidentally widened the span.

This detector flags inline-code spans where:
- The content has a leading or trailing space, **and**
- The content does *not* start (resp. end) with a backtick.

It only inspects single-backtick and double-backtick inline spans on lines
that are not inside fenced code blocks.

## Inputs
- One positional argument: path to a UTF-8 markdown file.

## Outputs
- One finding per offending span, written to stdout, in the form:
  `path:line:col {leading|trailing|both} whitespace inside inline code: <repr>`
- Summary line `findings: <N>` to stderr.

## Exit codes
- `0` — clean
- `1` — at least one finding
- `2` — usage / IO error

## Run
```
python3 detect.py examples/bad.md   # exit 1
python3 detect.py examples/good.md  # exit 0
```

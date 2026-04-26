# llm-output-non-breaking-space-leak-detector

Detects non-breaking spaces and other Unicode whitespace characters that LLMs
sometimes emit in place of a regular ASCII space.

## What it catches

| Codepoint | Name |
|---|---|
| U+00A0 | NO-BREAK SPACE (NBSP) |
| U+202F | NARROW NO-BREAK SPACE |
| U+2007 | FIGURE SPACE |
| U+2009 | THIN SPACE |
| U+200A | HAIR SPACE |
| U+3000 | IDEOGRAPHIC SPACE |

## Why it matters

These characters look like spaces but break:
- shell command copy-paste (`pip install` becomes `pip\xa0install` and fails)
- `grep` / `awk` / `cut` pipelines that split on `\s` or literal space
- tokenizer alignment (NBSP usually tokenizes differently from ASCII space)
- diff/blame heuristics

NBSP leaks are especially common in numeric+unit pairs (`12 ms`, `100 MB`)
because some style guides specify NBSP there, and the model picks that up
even when the surrounding context is code or shell.

## Usage

```
python3 detector.py <file> [<file>...]
```

Exits 0 on clean, 1 on hits, 2 on bad usage.

## Worked example

Input `worked-example.txt` (5 lines; 4 contain non-standard whitespace):

```
Install the package with pip<NBSP>install foo-bar.
The latency was 12<NARROW-NBSP>ms across 5 trials.
Use the flag --max-tokens<THIN-SPACE>1024 when calling the API.
A regular line with only ASCII spaces here.
Mixed<IDEOGRAPHIC-SPACE>ideographic space at end.
```

Real run:

```
$ python3 detector.py worked-example.txt
worked-example.txt:1:29: U+00A0 NO-BREAK SPACE
    context: 'Install the package with pip\xa0install foo-bar.'
worked-example.txt:2:19: U+202F NARROW NO-BREAK SPACE
    context: 'The latency was 12\u202fms across 5 trials.'
worked-example.txt:3:26: U+2009 THIN SPACE
    context: 'Use the flag --max-tokens\u20091024 when calling the API.'
worked-example.txt:5:6: U+3000 IDEOGRAPHIC SPACE
    context: 'Mixed\u3000ideographic space at end.'

FAIL: 4 non-standard whitespace leak(s) detected
```

Exit code: `1`.

## Remediation

Pipe through `tr` or a small replace pass before publishing:

```python
TRANS = str.maketrans({"\u00A0":" ", "\u202F":" ", "\u2007":" ",
                       "\u2009":" ", "\u200A":" ", "\u3000":" "})
clean = text.translate(TRANS)
```

Or, if the NBSPs are intentional (typography), gate the detector to only
fire inside fenced code blocks and inline code spans.

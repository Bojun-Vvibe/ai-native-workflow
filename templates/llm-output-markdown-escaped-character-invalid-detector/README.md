# llm-output-markdown-escaped-character-invalid-detector

## Problem

LLM output often contains backslash sequences that look like escapes but
aren't. CommonMark only treats `\X` as an escape when `X` is one of the ASCII
punctuation characters (`!"#$%&'()*+,-./:;<=>?@[\]^_\`{|}~`). Anything else —
`\d`, `\w`, `\n`, `\t`, `\z`, `\1` — is rendered with the backslash as a
literal character, which is almost never the model's intent. Common causes:

- The model leaks regex syntax (`\d`, `\w`, `\b`) into prose.
- The model emits `\n` / `\t` thinking markdown will turn them into a newline
  or tab.
- Windows-style paths (`C:\users\test`) get treated as escapes by readers
  copying out of the rendered view.

## Usage

```sh
python3 detector.py path/to/file.md
```

Exit code: `0` if no findings, `1` if any file had at least one finding.

The detector skips fenced code blocks (``` and `~~~`) and inline code spans,
because backslash escapes do not apply inside code.

## Worked example

```sh
$ python3 detector.py examples/bad.md
examples/bad.md:3:5: invalid escape '\\d'
examples/bad.md:3:25: invalid escape '\\w'
examples/bad.md:3:60: invalid escape '\\u'
examples/bad.md:3:66: invalid escape '\\t'
examples/bad.md:4:25: invalid escape '\\n'
examples/bad.md:12:14: invalid escape '\\z'

$ python3 detector.py examples/good.md
$ echo $?
0
```

(Exact column numbers may vary by one depending on whitespace; the important
thing is `bad.md` produces ≥1 finding and `good.md` produces zero.)

## Limitations

- Inline-code stripping is a regex approximation, not a full CommonMark
  parser. Pathological backtick patterns may produce false positives or
  negatives.
- Does not check escapes inside HTML blocks; treats them as prose.

# llm-output-fence-info-string-trailing-comma-detector

Detects fenced code-block opening lines whose **info string** (the
language tag) ends with stray punctuation: `,` `;` `:` `.` `!`.

LLMs often emit:

````
```python,
def f(): ...
```
````

The trailing comma turns the language tag into the literal string
`python,`, which no renderer recognizes — so the block silently falls
back to **plain text** with no syntax highlighting. The bug is invisible
in source view and only shows up when the markdown is rendered.

## How it works

For every line:

1. If not currently inside a fence, match `^\s{0,3}(`{3,}|~{3,})(.*)$`.
2. Strip the info string and check `^[A-Za-z0-9_+\-./]+([,;:.!])\s*$`.
3. If it matches, emit a finding with the captured punctuation.
4. Track fence open/close so info strings inside an open block are
   never mistaken for new openings.

Pure Python stdlib. Single pass. Deterministic.

## Run

```bash
python3 detector.py path/to/file.md [more.md ...]
```

Exit code:
- `0` — no findings
- `1` — at least one trailing-punctuation info string
- `2` — usage error

## Example output

```
$ python3 detector.py examples/bad.md
examples/bad.md:5: code fence info string 'python,' ends with ',' (language tag becomes unknown — strip the punctuation)
examples/bad.md:12: code fence info string 'bash;' ends with ';' (language tag becomes unknown — strip the punctuation)
examples/bad.md:18: code fence info string 'js:' ends with ':' (language tag becomes unknown — strip the punctuation)

3 finding(s).
$ echo $?
1
```

`examples/good.md` (same content with the trailing punctuation stripped)
exits `0`.

## Limitations

- Only the **single character** immediately before optional trailing
  whitespace is checked. Info strings with internal punctuation like
  `python title="x"` are ignored (info-string attributes are valid in
  some flavors).
- Does not validate that the language tag is a *known* language —
  that's the job of `llm-output-fence-language-tag-spelling-detector`.
- Tilde fences (`~~~`) are scanned identically to backtick fences.

# llm-output-fence-blank-line-spacing-validator

Pure-stdlib validator for blank-line spacing around fenced code
blocks in LLM-generated Markdown. Catches the bug class where the
fence renders as literal backticks (or eats the surrounding line)
because CommonMark / GitHub-Flavored Markdown require a blank line
before and after a fenced code block.

## Why this exists

LLMs glue fences directly to surrounding prose all the time:

```
The function returns a tuple of `(ok, error)`:
```python
def call():
    return True, None
```
After the call, you can inspect the result.
```

In the streaming preview this looks fine. At render time:

- **CommonMark / pandoc**: the leading ` ``` ` is consumed as the
  end of the previous paragraph; the code is rendered as part of
  the paragraph in code-span style, and the closing fence becomes
  literal backticks visible to the reader.
- **GitHub Flavored Markdown**: more forgiving in some cases but
  inconsistent across the web UI, the API, and Jupyter rendering.
- **Slack canvas / Notion / Linear**: each has its own quirks; the
  one thing they all agree on is that a blank line on both sides
  works everywhere.

The reverse pattern — multiple blank lines around the fence — is
a style finding only. It renders correctly but bloats the diff.

## Detected kinds

| Kind | Trigger | Severity |
|---|---|---|
| `missing_blank_before` | opening fence has a non-blank line directly above | correctness — exit 1 |
| `missing_blank_after` | closing fence has a non-blank line directly below | correctness — exit 1 |
| `extra_blank_before` | more than one blank line above the opener | style — exit 0 |
| `extra_blank_after` | more than one blank line below the closer | style — exit 0 |

The validator is paired with — but does not duplicate —
`llm-output-orphan-fence-detector` (unterminated fences) and
`llm-output-fence-language-tag-spelling-detector` (info-string
typos). Together they cover the three independent fence bug axes.

## How to run

```bash
python3 detector.py example/bad.md   # exit 1, 4 findings
python3 detector.py example/good.md  # exit 0
python3 detector.py -                 # read stdin
```

Stdlib only. Python 3.8+. No third-party Markdown parser; the
fence detector is a regex against `^(\s{0,3})(`{3,}|~{3,})`,
matching the CommonMark fence rule (up to 3 leading spaces, run of
3+ backticks or tildes).

Start-of-file and end-of-file are treated as implicit blank lines
so a document that opens or closes with a fence does not flag.

## Example output

`example/bad.md` exercises all four kinds. Verbatim:

```
$ python3 detector.py example/bad.md
line 5: missing_blank_before
  opening fence on line 5 has non-blank line 4 above ('The function returns a tuple of `(ok, error)`:'); CommonMark requires a blank line before a fenced code block
line 8: missing_blank_after
  closing fence on line 8 has non-blank line 9 below ('After the call, you can inspect the result.'); CommonMark requires a blank line after a fenced code block
line 17: extra_blank_before
  opening fence on line 17 has 3 blank lines above (expected 1)
line 20: extra_blank_after
  closing fence on line 20 has 3 blank lines below (expected 1)

FAIL: 2 fence-spacing correctness finding(s) (+ 2 style finding(s))
```

`example/good.md` is the same content with one blank line on each
side of every fence:

```
$ python3 detector.py example/good.md
OK: fence blank-line spacing is correct
```

Four findings on `bad.md` (2 correctness + 2 style), zero on
`good.md`.

## Tuning

- **Treat style findings as warnings**: the script already exits 0
  when only `extra_*` kinds fire. Pipe through `grep -v WARN` if
  you want CI to be silent on style.
- **Tighter mode**: post-filter `Hit` for `kind.startswith("missing_")`
  only and ignore the rest.
- **Looser mode**: skip the validator entirely on documents whose
  first non-empty line is `<!-- markdownlint-disable -->` or any
  other opt-out marker your house style defines; the validator
  itself does not parse HTML comments by design.

## Composition

- **`llm-output-orphan-fence-detector`** — orthogonal axis (count of
  fences, not spacing). Run both; they share no findings.
- **`llm-output-fence-language-tag-spelling-detector`** — info-string
  hygiene. Run after this validator so the parser sees well-formed
  fences first.
- **`agent-output-validation`** — feed `(line_no, kind)` into a
  one-turn repair prompt: *"insert a blank line before line 5"*.
  Deterministic fix; rerun this validator as the verifier.
- **`structured-error-taxonomy`** — `missing_blank_before` and
  `missing_blank_after` are `do_not_retry / attribution=model`
  (the model emitted invalid Markdown; retrying without an explicit
  format instruction reproduces the bug). The two `extra_*` kinds
  are pure style and never warrant a retry.

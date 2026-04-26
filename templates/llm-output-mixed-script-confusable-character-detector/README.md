# llm-output-mixed-script-confusable-character-detector

Flags **mixed-script tokens** in LLM output — words that contain ASCII Latin
letters mixed with non-Latin lookalikes (Cyrillic, Greek, fullwidth Latin).
These are a frequent artifact of multilingual model training and silently
break:

- code identifiers (`setTimeout` vs `setTim`+Cyrillic-`е`+`out`)
- shell commands copy-pasted from chat
- URL hostnames (homograph attacks)
- grep / search workflows downstream of the LLM

The detector deliberately **ignores pure non-Latin tokens** (e.g. an
intentional Russian word) — it only flags *mixing* inside one whitespace-
separated token, where the intent was clearly Latin.

## Usage

```sh
python3 detector.py path/to/file.txt    # exit 1 on any defect
cat file.txt | python3 detector.py -    # stdin
```

## Worked example

Input: [`example/sample.txt`](example/sample.txt) — 11 lines including
deliberate Cyrillic, Greek, and fullwidth lookalikes plus one pure-Russian
control line.

Run:

```sh
$ python3 detector.py example/sample.txt
```

Actual stdout (exit code `1`):

```
line 3 col 11: Cyrillic U+0435 (CYRILLIC SMALL LETTER IE) looks like ASCII 'e'
  token: 'setTimеout'
line 8 col 15: Greek U+03B1 (GREEK SMALL LETTER ALPHA) looks like ASCII 'a'
  token: 'clαss'
line 8 col 25: Greek U+03B1 (GREEK SMALL LETTER ALPHA) looks like ASCII 'a'
  token: 'MyClαss()'
line 9 col 12: Fullwidth U+FF46 (FULLWIDTH LATIN SMALL LETTER F) looks like ASCII 'f'
  token: 'ｆoo'
line 11 col 19: Cyrillic U+0435 (CYRILLIC SMALL LETTER IE) looks like ASCII 'e'
  token: '/usеrs/profile'

FAIL: 5 confusable character(s) in mixed-script tokens
```

Note that line 10 (`Pure Russian word привет should be ignored.`) is correctly
**not** flagged — the Russian word contains no ASCII Latin letters, so it's
treated as intentional.

## Confusable map

The bundled map is small but covers the most common offenders:

- Cyrillic lower/upper that look like Latin (а е о р с х у і ј / А Е О Р С Х Н К М Т В)
- Greek (α ο ρ ι Α Β Ε Ο Ρ Τ)
- Fullwidth Latin block (U+FF21–FF5A)

Extend `CONFUSABLES` in `detector.py` for your domain. The Unicode
[confusables.txt](https://www.unicode.org/Public/security/) is the
authoritative source if you need exhaustive coverage.

## When to wire this in

- Right before any LLM-generated code is pasted into a file or run.
- Pre-commit hook on directories that hold LLM-generated docs or commit
  messages.
- Inside an agent loop, as a final-output sanity check.

## Limits

- Does not flag pure-script tokens. A whole sentence written in Cyrillic
  passes silently — pair with a language detector if that matters.
- Does not normalize via `unicodedata.normalize('NFKC', ...)`; do that
  upstream if you want to *fix* (rather than detect) confusables.
- Only inspects whitespace-delimited tokens. Inline confusables inside
  triple-backtick code blocks are still detected because the tokenizer is
  whitespace-based.

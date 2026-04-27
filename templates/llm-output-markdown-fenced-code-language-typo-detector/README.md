# llm-output-markdown-fenced-code-language-typo-detector

Detects probable typos in fenced code language tags in Markdown — e.g.
` ```pyhton ` (transposition of `python`), ` ```javscript ` (deletion
in `javascript`), ` ```tyepscript ` (transposition in `typescript`).

## Why this matters

LLMs sometimes hallucinate slightly misspelled language tags. These look
plausible to a human skim, but every syntax highlighter falls back to
"no highlighting" because the tag matches no known language. The
canonicalization detector in this repo only handles known *aliases*
(`py` → `python`); it cannot catch a true misspelling. The blank-tag
detector only handles the empty case. This detector fills the gap
between them.

## What it detects

For each opening fence, the first whitespace-delimited info-string token
is normalized to lowercase. If the token is:

* in the known set of canonical names + common aliases → ignored
* within Damerau-Levenshtein distance 1 of any known token → flagged
  with the nearest match as suggestion
* unknown but far from anything known (e.g. an internal DSL name) →
  ignored to keep false-positive rate low

Damerau-Levenshtein counts a single adjacent transposition as one edit,
so `pyhton` (h↔t swap) is correctly classified as one edit from `python`.

## Code-fence awareness

The scanner tracks open/close state across the document. A fenced block
opened with N backticks is closed only by ≥N backticks of the same kind
on a line by themselves. Any fence-looking line *inside* an open block
is treated as content, not as a new opening, so typoed tags shown as
documentation examples inside an outer ` ```` ` block are NOT flagged.

## How to run

```bash
python3 detect.py example/bad.md
```

Exit codes:

* `0` — clean
* `1` — one or more findings printed to stdout
* `2` — usage / IO error

## CI usage

```yaml
- name: Lint markdown code-fence language typos
  run: |
    find docs -name '*.md' -print0 | \
      xargs -0 -n1 python3 templates/llm-output-markdown-fenced-code-language-typo-detector/detect.py
```

## Worked example

`example/bad.md` contains 3 typoed tags (`pyhton`, `javscript`,
`tyepscript`), 1 canonical tag, 1 alias, 1 unknown-but-distant tag, and
1 typoed tag *inside* an outer fenced block. Running the detector
produces `example/expected-output.txt` verbatim and exits with status
`1`.

`example/good.md` exercises the same surface with only canonical tags
and aliases. The detector exits `0` with no output.

## Customising

Edit the `KNOWN` frozenset in `detect.py` to add the languages your
project actually uses. Add internal DSL names there to silence false
positives that happen to land within edit-distance 1 of a real
language.

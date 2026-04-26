# llm-output-numeric-thousands-separator-consistency-validator

Pure-stdlib validator for thousands-separator consistency across the
numeric literals in an LLM-generated document. Catches the silent-
corruption class where one paragraph writes `1,000` and another writes
`1000` (or, worse, `1.000` in the European convention) — the prose
reads fluently but a downstream consumer that splits and parses these
spans (a CSV emitter, a chart generator, a financial summariser, a
RAG that pivots on numeric facts) will silently get half its inputs
wrong.

## What it catches

| kind | what it catches |
|---|---|
| `mixed_styles` | the document uses two or more of `{comma, dot, space}` as thousands separators (e.g. `1,234` and `1.234` both appear). Fires once per minority-style number. |
| `inconsistent_unseparated` | at least one number uses a separator and another number with ≥4-digit integer part uses none (e.g. `1,000` and `12500` in the same doc). Fires once per offending unseparated number. |

`ok` is `False` iff any finding fires.

## Why a separate template

Adjacent siblings cover different layers:

- `llm-output-citation-bracket-balance-validator` — paired-delimiter
  discipline for citations, not numeric-literal convention.
- generic locale validators — usually require the document to declare
  a locale up front, then validate against it. This template is
  *self-contained*: it infers the document's intended convention from
  its own majority and flags the deviations.

## Design choices

- **Self-contained majority inference.** No locale config, no
  declared convention. Whichever separator style appears most often
  becomes the implicit "expected" style; minorities are flagged.
  This matches how the bug actually shows up: the model emits
  *most* numbers in one style and slips on a few.
- **Short numbers don't count.** A literal like `999` or `42` cannot
  be inconsistent with anything (no separator was needed). They are
  not even returned in `numbers`.
- **Decimals are recognised and stripped before classification.** A
  trailing 1–2 digit tail after a comma or dot is treated as decimal,
  so `1,234.50` classifies as `comma` (US) and `1.234,50` as `dot`
  (EU). A 4+ digit tail is also forced to decimal — group separators
  cannot be 4 long.
- **Skip code spans, fenced blocks, and URLs.** Inline `` `...` ``,
  fenced ``` blocks, and `http(s)://...` runs are masked out before
  scanning. A `MAX = 100000` inside a code block won't trigger
  `inconsistent_unseparated`; a path like `/items/12345` inside a URL
  won't trigger anything.
- **Boundary discipline.** A digit run preceded by a letter (e.g.
  `abc123`) is not started — those are identifiers, not numeric
  literals. Combined with URL masking, this kills the obvious
  version-string false positives.
- **Deterministic output.** Findings sorted by `(kind, pos, detail)`.
  Two runs over the same input produce byte-identical JSON.
- **Eager refusal on bad input.** Non-`str` raises
  `ThousandsSeparatorValidationError` immediately. Empty text is
  *valid* (no numbers, no findings).
- **Pure function.** No I/O, no clocks, no transport.
- **Stdlib only.** `dataclasses`, `json`. No `re`.

## Composition

- Run *before* any pipeline that pivots on numeric facts (chart
  generators, financial summarisers, CSV emitters). A `mixed_styles`
  finding is the cheapest signal that downstream parsing will silently
  diverge from intent.
- Pair with `llm-output-fence-extractor` if you need the cleaned prose
  for further analysis — though this template already strips fenced
  code internally, so it is safe to run on raw model output.
- Pair with `agent-decision-log-format`: one log line per finding,
  sharing `pos` so a reviewer jumps straight to the offending span.

## How to run

```
python3 example.py
```

No arguments. No external dependencies. Tested on Python 3.9+.

## Worked example

Eight cases — clean comma-only, comma vs unseparated, comma vs dot,
all-short numbers, decimals, code-span-masked, URL-masked, and
fenced-block-masked. Output below captured verbatim from
`python3 example.py`.

```
# llm-output-numeric-thousands-separator-consistency-validator — worked example

## case 01_clean_comma_throughout
text:
  | Revenue grew from 1,000 to 12,500 over the year, peaking at 1,234,567 in Q4.
{
  "findings": [],
  "numbers": [
    {
      "integer_part_digits": 4,
      "pos": 18,
      "raw": "1,000",
      "style": "comma"
    },
    {
      "integer_part_digits": 5,
      "pos": 27,
      "raw": "12,500",
      "style": "comma"
    },
    {
      "integer_part_digits": 7,
      "pos": 60,
      "raw": "1,234,567",
      "style": "comma"
    }
  ],
  "ok": true,
  "style_counts": {
    "ambiguous": 0,
    "comma": 3,
    "dot": 0,
    "none": 0,
    "space": 0
  }
}

## case 02_mixed_comma_and_unseparated
text:
  | We shipped 1,000 units in March and 12500 units in April. The April count is suspect.
{
  "findings": [
    {
      "detail": "'12500' (5 digits) has no separator but document elsewhere uses ['comma']",
      "kind": "inconsistent_unseparated",
      "pos": 36
    }
  ],
  "numbers": [
    {
      "integer_part_digits": 4,
      "pos": 11,
      "raw": "1,000",
      "style": "comma"
    },
    {
      "integer_part_digits": 5,
      "pos": 36,
      "raw": "12500",
      "style": "ambiguous"
    }
  ],
  "ok": false,
  "style_counts": {
    "ambiguous": 1,
    "comma": 1,
    "dot": 0,
    "none": 0,
    "space": 0
  }
}

## case 03_mixed_comma_and_dot
text:
  | Sales were 1,234 in the US report and 1.234 in the EU report — same number, different convention.
{
  "findings": [
    {
      "detail": "'1.234' uses 'dot' separator; document majority is 'comma'",
      "kind": "mixed_styles",
      "pos": 38
    }
  ],
  "numbers": [
    {
      "integer_part_digits": 4,
      "pos": 11,
      "raw": "1,234",
      "style": "comma"
    },
    {
      "integer_part_digits": 4,
      "pos": 38,
      "raw": "1.234",
      "style": "dot"
    }
  ],
  "ok": false,
  "style_counts": {
    "ambiguous": 0,
    "comma": 1,
    "dot": 1,
    "none": 0,
    "space": 0
  }
}

## case 04_short_numbers_dont_count
text:
  | There were 5 cats, 17 dogs, and 999 birds. No separator needed for any of them.
{
  "findings": [],
  "numbers": [],
  "ok": true,
  "style_counts": {
    "ambiguous": 0,
    "comma": 0,
    "dot": 0,
    "none": 0,
    "space": 0
  }
}

## case 05_decimals_are_handled
text:
  | The price moved from 1,234.50 to 1,500.00, a small change. Volume hit 2,000,000 shares.
{
  "findings": [],
  "numbers": [
    {
      "integer_part_digits": 4,
      "pos": 21,
      "raw": "1,234.50",
      "style": "comma"
    },
    {
      "integer_part_digits": 4,
      "pos": 33,
      "raw": "1,500.00",
      "style": "comma"
    },
    {
      "integer_part_digits": 7,
      "pos": 70,
      "raw": "2,000,000",
      "style": "comma"
    }
  ],
  "ok": true,
  "style_counts": {
    "ambiguous": 0,
    "comma": 3,
    "dot": 0,
    "none": 0,
    "space": 0
  }
}

## case 06_code_spans_ignored
text:
  | Set `port=8080` and `timeout=30000`. Real numbers in prose: we processed 1,000 events.
{
  "findings": [],
  "numbers": [
    {
      "integer_part_digits": 4,
      "pos": 73,
      "raw": "1,000",
      "style": "comma"
    }
  ],
  "ok": true,
  "style_counts": {
    "ambiguous": 0,
    "comma": 1,
    "dot": 0,
    "none": 0,
    "space": 0
  }
}

## case 07_url_ignored
text:
  | See https://example.com/v1/items/12345 for the API; production handled 1,000,000 calls today.
{
  "findings": [],
  "numbers": [
    {
      "integer_part_digits": 7,
      "pos": 71,
      "raw": "1,000,000",
      "style": "comma"
    }
  ],
  "ok": true,
  "style_counts": {
    "ambiguous": 0,
    "comma": 1,
    "dot": 0,
    "none": 0,
    "space": 0
  }
}

## case 08_fenced_code_ignored
text:
  | We hit production:
  | 
  | ```
  | MAX = 100000
  | MIN = 0
  | ```
  | 
  | In prose: 50,000 records were processed and 25,000 were rejected.
{
  "findings": [],
  "numbers": [
    {
      "integer_part_digits": 5,
      "pos": 60,
      "raw": "50,000",
      "style": "comma"
    },
    {
      "integer_part_digits": 5,
      "pos": 94,
      "raw": "25,000",
      "style": "comma"
    }
  ],
  "ok": true,
  "style_counts": {
    "ambiguous": 0,
    "comma": 2,
    "dot": 0,
    "none": 0,
    "space": 0
  }
}
```

## Files

- `example.py` — the validator + the runnable demo.
- `README.md` — this file.

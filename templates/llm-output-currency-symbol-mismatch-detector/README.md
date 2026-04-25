# llm-output-currency-symbol-mismatch-detector

Pure stdlib detector for currency-symbol vs currency-code contradictions
in free-text LLM output. Catches the failure modes that silently corrupt
downstream "extract the price into a structured field" steps when the
model writes `$50 EUR`, `€75 USD`, or a bare `$499` in a document that
mixes USD and CAD.

## Why this matters

LLMs frequently mix currency markers — a fragment from a USD source
glued onto a EUR template, or a model that learned the locale-fluid
phrase `$50 (Canadian dollars)` and then dropped the parenthetical. The
extracted record then arbitrarily picks one or the other and posts to
finance with the wrong magnitude. The text **renders fine to a human
reader who tolerates the redundancy**; the parser does not.

## Findings

Deterministic order: `(kind, start_offset)`.

| kind | severity | what it catches |
|---|---|---|
| `symbol_code_mismatch` | hard | `$50 EUR`, `€75 USD`, `£10 JPY` — symbol's canonical code contradicts the explicit code within `window_chars` |
| `ambiguous_dollar_sign` | hard | bare `$50` with no nearby code in a document that mentions ≥2 dollar-zone codes (USD/CAD/AUD/HKD/...) so `$` cannot be safely resolved |
| `duplicate_currency` | hard | `USD $1,200 USD` — same code repeated around an amount, classic paste-merge bug |
| `sign_position_swap` | hard | `50$` instead of `$50` for symbols that canonically prefix in en-US — locale-bleed signal |
| `unknown_currency_code` | warn | currency-shaped 3-letter code adjacent to an amount but not in `allowed_codes` (e.g. BTC accidentally shipped in a fiat-only pipeline) |

`ok` is `False` iff any **hard** finding fires. `unknown_currency_code`
is a warning — caller decides via `report.kinds()`.

## Design choices

- **`$` is intentionally NOT in the symbol→code table.** A bare `$` is
  ambiguous (USD/CAD/AUD/HKD/NZD/SGD/MXN). The detector has a separate
  rule: if the document mentions ≥2 dollar-zone codes anywhere, then a
  bare `$` amount with no nearby code is flagged. This is deliberately
  asymmetric — the symbol→code mismatch rule for `$` only fires when
  the nearby code is a *non-dollar-zone* code (e.g. `$50 EUR`), never
  on `$50 CAD` (which is locally consistent).
- **`€` is excluded from `sign_position_swap`.** fr-FR and de-DE
  canonically write `50 €`. Flagging that as a swap would generate
  noise on legitimately-localized output.
- **Window-bounded code search.** Adjacency is `window_chars` (default
  8). A code 30 chars away is not "attached" to the amount and the
  detector should not pair them — that would false-positive on every
  paragraph that mentions multiple currencies.
- **Eager refusal on bad input.** `text` not a string raises
  `CurrencyValidationError`. A silent empty report would be worse.
- **Pure function.** No I/O, no clocks, no transport. Composes anywhere.
- **Stdlib only.** `re`, `dataclasses`, `json` — nothing to install.

## Composition

- `agent-output-validation` checks JSON envelope shape (is there a
  `prose` field?). This template scans the prose itself.
- `structured-output-repair-loop` can take a `symbol_code_mismatch`
  finding and feed it back as a one-shot repair hint ("you wrote
  `$50 EUR` — pick one or the other").
- `llm-output-trust-tiers` — `symbol_code_mismatch` and
  `ambiguous_dollar_sign` should force `source_class=fresh` and
  generally route to `human_review` when the blast radius is anything
  finance-shaped.
- `structured-error-taxonomy` — these classify as `attribution=tool`
  (model bug), `retryability=do_not_retry_same_prompt` (a temperature
  retry rarely fixes it; the prompt needs to be tightened to demand
  "one currency marker per amount").

## Run

```bash
python3 templates/llm-output-currency-symbol-mismatch-detector/example.py
```

Pure stdlib. No `pip install`. Six worked cases covering every finding
class plus one clean baseline.

## Example output:

```
--- 01 clean USD ---
{
  "ok": true,
  "text_length": 47,
  "findings": []
}

--- 02 symbol_code_mismatch ---
{
  "ok": false,
  "text_length": 52,
  "findings": [
    {
      "kind": "symbol_code_mismatch",
      "start": 15,
      "end": 18,
      "snippet": "$50 ... EUR",
      "detail": "$ amount labeled with non-dollar-zone code EUR"
    }
  ]
}

--- 03 ambiguous_dollar_sign ---
{
  "ok": false,
  "text_length": 105,
  "findings": [
    {
      "kind": "ambiguous_dollar_sign",
      "start": 68,
      "end": 72,
      "snippet": "$499",
      "detail": "bare $ amount with no nearby code; document mentions ['CAD', 'USD'] so $ is ambiguous"
    }
  ]
}

--- 04 duplicate_currency ---
{
  "ok": false,
  "text_length": 44,
  "findings": [
    {
      "kind": "duplicate_currency",
      "start": 17,
      "end": 23,
      "snippet": "ng: USD $1,200 USD pos",
      "detail": "code USD appears 2 times around amount"
    }
  ]
}

--- 05 sign_position_swap + unknown ---
{
  "ok": false,
  "text_length": 50,
  "findings": [
    {
      "kind": "sign_position_swap",
      "start": 14,
      "end": 17,
      "snippet": "50$",
      "detail": "symbol $ appears after amount; canonical en-US position is prefix"
    },
    {
      "kind": "unknown_currency_code",
      "start": 38,
      "end": 41,
      "snippet": "BTC",
      "detail": "code BTC not in allowed_codes"
    }
  ]
}

--- 06 euro vs USD ---
{
  "ok": false,
  "text_length": 30,
  "findings": [
    {
      "kind": "symbol_code_mismatch",
      "start": 11,
      "end": 14,
      "snippet": "\u20ac75 ... USD",
      "detail": "symbol \u20ac -> EUR contradicts adjacent code USD"
    }
  ]
}

=== summary ===
case 01: ok=True kinds=[]
case 02: ok=False kinds=['symbol_code_mismatch']
case 03: ok=False kinds=['ambiguous_dollar_sign']
case 04: ok=False kinds=['duplicate_currency']
case 05: ok=False kinds=['sign_position_swap', 'unknown_currency_code']
case 06: ok=False kinds=['symbol_code_mismatch']
```

The output proves the design rules:
- **Case 01**: clean en-US output (`$99.00 USD`) — `$` is locally consistent with the dollar-zone code `USD`, no finding fires (the `$ → non-dollar-zone` rule is asymmetric on purpose).
- **Case 02**: `$50 EUR` is flagged because `EUR` is *not* a dollar-zone code, so the symbol contradicts the explicit code.
- **Case 03**: a bare `$499` would normally be silent, but the document already mentions both `USD` and `CAD`, so the detector can prove `$` is ambiguous *for this document* and flags it.
- **Case 04**: `USD $1,200 USD` triggers `duplicate_currency` exactly once at the amount span — the snippet captures the whole window so a reviewer sees the redundancy.
- **Case 05**: postfix `50$` triggers `sign_position_swap` (en-US convention) and the adjacent `BTC` is flagged because it's outside the default fiat-only allowlist — two independent findings on one sentence.
- **Case 06**: `€75 USD` — symbol `€` resolves to `EUR` and contradicts the explicit `USD`, exactly the same shape as case 02 but with a different mismatch direction.

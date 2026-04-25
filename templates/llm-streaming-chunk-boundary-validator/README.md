# llm-streaming-chunk-boundary-validator

Pure stdlib post-hoc validator for *recorded* streamed chunk sequences
(SSE / NDJSON / raw token streams from an LLM). Catches the four
classes of boundary split that silently corrupt downstream consumers
even when the underlying byte content is correct after reassembly:

- **`utf8_split`** — a chunk's tail bisects a multi-byte UTF-8
  sequence. Terminal renders mojibake for one tick; a naive byte-by-byte
  JSON parser blows up at the next `.decode("utf-8")` call.
- **`inside_string`** — in `mode="json"`, the boundary lands inside a
  JSON string literal. A streaming JSON repair / extraction layer may
  emit a half-string token to the UI before the close-quote arrives.
- **`escape_split`** — in `mode="json"`, the boundary lands immediately
  after a `\` escape character; the escapee (e.g. `n`) is the first
  byte of the next chunk. A line-buffered consumer that decodes early
  emits a literal backslash, then a literal `n`, instead of the
  intended newline.
- **`codepoint_grapheme`** — a chunk straddles a Zero-Width Joiner
  (U+200D) inside a family/profession emoji sequence (e.g.
  `👨‍👩‍👧`). The terminal renders three separate glyphs for ~150ms.
  Soft warning, but it flips `ok=False`.

This is the **regression / fixture validator** that proves your splits
are safe before the change ships. It does not own the transport — pair
with `streaming-chunk-reassembler` (transport correctness) and
`partial-json-streaming-parser` (consumer-side recovery).

## When to use

- Capture chunk sequences from a model+adapter combination you intend
  to ship. Run the validator over the recorded fixtures in CI. A
  regression in the model's tokenizer or the SSE adapter's flush logic
  shows up as `findings_kind_totals[utf8_split]` going from `0 → N`
  immediately, not weeks later when a user reports "your chat shows
  weird ▢ characters."
- Soak-test a custom batching / coalescing layer that re-splits the
  upstream chunks. Run the validator on its output to prove your
  re-flush points respect codepoint and JSON-string boundaries.
- Sanity-check a third-party SSE proxy you just put in the path.

## When NOT to use

- This is **not** a replacement for `streaming-utf8-boundary-buffer`.
  That template *fixes* mid-codepoint splits at the consumer; this one
  *detects* them so you know whether the buffer is needed at all.
- This is **not** a streaming JSON parser. It walks a tiny state
  machine for `(in_string, escape)` only. For full incremental parsing
  use `partial-json-streaming-parser`.
- Pure post-hoc — does not touch the network or sockets.

## Design choices worth knowing

- **Mode-gated rules.** `mode="text"` runs only the two bytes-only
  checks (utf8_split, codepoint_grapheme); `mode="json"` adds the
  state-machine checks. A free-form prose stream should not be
  penalized for not looking like JSON.
- **Multiple findings per boundary are allowed.** Case 06 in the
  worked example reports both `escape_split` *and* `inside_string` for
  the same boundary, because both are real and they tell the consumer
  two different things. Findings are sorted `(boundary_index, kind)`
  so two runs on the same input are byte-identical (cron-friendly
  diffing).
- **Soft warning still flips `ok=False`.** The four-finding-kind taxonomy
  is uniform: any anomaly is `ok=False`. If you want to ignore
  `codepoint_grapheme`, filter the report's `findings` tuple in the
  caller — explicit beats hidden severity tiers.
- **No grapheme cluster library.** A real ICU-aware grapheme walker
  would catch many more split cases (regional indicator pairs, Indic
  conjuncts). The ZWJ check covers the *common* offender (family
  emoji) and is stdlib-only. Treat the warning as a signal to switch
  to `regex` / ICU if you ship to surfaces that must render emoji
  perfectly.
- **Streaming JSON state survives across boundaries.** `inside_string`
  / `escape` flags are carried from boundary `i` into the scan of
  chunk `i+1`, so a boundary at the *exact* close-quote correctly
  reports neither.

## Composes with

- **`streaming-chunk-reassembler`** — the reassembler proves bytes are
  delivered exactly once in seq order; this validator proves they're
  *split* at safe places.
- **`streaming-utf8-boundary-buffer`** — if `utf8_split` count is
  consistently > 0 for an upstream you don't control, slot the buffer
  in front of your consumer.
- **`partial-json-streaming-parser`** — `inside_string` /
  `escape_split` counts > 0 are the signal that you need an
  incremental parser instead of `json.loads(buf)` per chunk.
- **`structured-error-taxonomy`** — all four kinds map to
  `attribution=tool` (the upstream emitter) with
  `retryability=do_not_retry` (the bytes are already on the wire; the
  fix is in the splitter, not in retry).

## Adapt this section

- `_ZWJ` — extend with regional-indicator pair detection (flag emoji
  are two regional indicators that must stay together) if your surface
  renders them.
- The JSON state machine is a 25-line scanner; if your structured
  output uses a different framing (e.g. NDJSON with `\n`-delimited
  records) extend `_scan_json_state` to also reset the in-string flag
  on record boundaries.

## Worked example

`example.py` runs six recorded streams — clean baselines for both
modes plus one case for each finding class.

### Worked example output

```
========================================================================
01 clean text  (mode=text)
========================================================================
{
  "boundary_count": 2,
  "chunk_count": 3,
  "findings": [],
  "mode": "text",
  "ok": true
}

========================================================================
02 utf8_split  (mode=text)
========================================================================
{
  "boundary_count": 1,
  "chunk_count": 2,
  "findings": [
    {
      "boundary_index": 0,
      "detail": "leader 0xE4 expects 3-byte sequence, only 1 byte(s) before chunk boundary",
      "kind": "utf8_split"
    }
  ],
  "mode": "text",
  "ok": false
}

========================================================================
03 codepoint_grapheme  (mode=text)
========================================================================
{
  "boundary_count": 1,
  "chunk_count": 2,
  "findings": [
    {
      "boundary_index": 0,
      "detail": "ZWJ (U+200D) straddles boundary; emoji sequence will render as separate glyphs in the consumer for one tick",
      "kind": "codepoint_grapheme"
    }
  ],
  "mode": "text",
  "ok": false
}

========================================================================
04 clean json  (mode=json)
========================================================================
{
  "boundary_count": 2,
  "chunk_count": 3,
  "findings": [],
  "mode": "json",
  "ok": true
}

========================================================================
05 inside_string  (mode=json)
========================================================================
{
  "boundary_count": 1,
  "chunk_count": 2,
  "findings": [
    {
      "boundary_index": 0,
      "detail": "boundary lands inside a JSON string literal; a naive consumer may emit a partial string token",
      "kind": "inside_string"
    }
  ],
  "mode": "json",
  "ok": false
}

========================================================================
06 escape_split  (mode=json)
========================================================================
{
  "boundary_count": 1,
  "chunk_count": 2,
  "findings": [
    {
      "boundary_index": 0,
      "detail": "boundary lands immediately after a JSON `\\` escape; the escapee byte is the first byte of the next chunk",
      "kind": "escape_split"
    },
    {
      "boundary_index": 0,
      "detail": "boundary lands inside a JSON string literal; a naive consumer may emit a partial string token",
      "kind": "inside_string"
    }
  ],
  "mode": "json",
  "ok": false
}

========================================================================
summary
========================================================================
{
  "finding_kind_totals": {
    "codepoint_grapheme": 1,
    "escape_split": 1,
    "inside_string": 2,
    "utf8_split": 1
  }
}
```

Notice case 06 reports **both** `escape_split` and `inside_string` for
the same boundary — that's not noise, those are two independent
problems at one cut point and the consumer needs to handle each. The
sort key `(boundary_index, kind)` puts them deterministically next to
each other so the alert diff is stable.

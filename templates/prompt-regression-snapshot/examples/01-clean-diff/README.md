# Example 01 — clean diff (no observable change)

## Setup

Three fixtures (`001-extract-user`, `002-summarise-pr`,
`003-classify-intent`). Each has two `mock_outputs` keyed by
`prompt_sha`:

- `v1` and `v2` outputs differ in **whitespace and key order**
  but are **canonically identical**.

This simulates a system-prompt change that doesn't affect the
model's structured output — e.g. you tightened the prose
description but the model emits the same JSON.

## Bootstrap

```sh
python3 ../../bin/snapshot.py \
    --fixtures fixtures --snapshots snapshots --prompt-sha v1 \
    run --write-new
```

Three snapshots are written under `snapshots/`.

## Run with v2

```sh
python3 ../../bin/snapshot.py \
    --fixtures fixtures --snapshots snapshots --prompt-sha v2 \
    run --strict
```

Expected output:

```
Snapshot run @ prompt_sha=v2 model=mock-1
Cases: 3  MATCH=3  CHANGED=0  NEW=0  MISSING=0

  MATCH    001-extract-user
  MATCH    002-summarise-pr
  MATCH    003-classify-intent
```

Exit code: `0`. CI passes.

## What this example demonstrates

- Canonicalisation absorbs **non-semantic** differences
  (whitespace, JSON key order). Reviewers don't drown in
  cosmetic diffs.
- A prompt change that doesn't affect output requires **zero**
  human review. Snapshots stay valid; CI is green.
- The optional next step `python3 ../../bin/snapshot.py
  --prompt-sha v2 rebless` updates the `prompt_sha` field on
  all MATCH snapshots so future runs can pin against v2.

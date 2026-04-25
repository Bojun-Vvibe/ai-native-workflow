# embedding-dimension-mismatch-guard

Pre-flight guard against the most common silent failure in retrieval-augmented
systems: **the index was built against one embedding model, the query is
being embedded with a different one** (different dim, different metric,
different normalization contract — sometimes all three at once).

## Why this template exists

Vector store SDKs handle dim mismatches in three different ways and none of
them are good:

1. **Hard reject at query time** — best case. Comes weeks after the bad
   write that filled the index with the wrong-shape vectors.
2. **Silent truncate or zero-pad** — worst case. Returns plausible-looking
   neighbors and recall degrades by 30–80% with no error surfaced anywhere.
3. **Dimension-implicit indexes** that infer the schema from the first vector
   written — failure is invisible until the *second* model writes to it.

A `dim_mismatch` is also only one of four ways the contract can break:

- `model_id_mismatch` — someone deployed `embedder-v3` to staging and forgot
  to rebuild the index. Dims may even still happen to match by coincidence.
- `dim_mismatch` — the silent-truncation bug above.
- `metric_mismatch` — same dims, but cosine vs dot vs L2 silently changes
  the score distribution and ranking.
- `normalization_mismatch` — index was built assuming normalized vectors
  (cosine math is a dot product), model returns un-normalized — recall
  degrades silently.

This guard returns one of five verdicts (the four above plus `ok`) so each
maps to a different recovery path. "The dims happen to match by coincidence"
is *not* `ok`.

## Hard rules

- **Pure stdlib** (`dataclasses`, `hashlib`).
- **No I/O, no network** — caller hands in `ModelSpec` and `IndexSpec`,
  both small frozen records read from existing config.
- **Specs are construction-validated**: `dim <= 0`, unknown `metric`, or
  empty `model_id` raise `GuardConfigError` at construction, not silently
  on first use.
- **First-mismatch-wins**, in this priority: `model_id` → `dim` → `metric`
  → `normalize`. The reason string points at the *root cause*, not the
  cascade — if the model id is wrong, "metric also differs" is noise.
- **`content_fingerprint`** (12-hex-char sha256 of the four contract
  fields) lets the orchestrator stamp every embedding it writes; on read,
  any mismatch surfaces immediately rather than at recall-evaluation time
  three weeks later.
- **Bulk-write per-vector dim sweep**: even when the spec contract matches,
  any individual upserted vector with the wrong length poisons the index.
  `check_upsert` rejects the *whole* batch and returns the offending
  indices so the caller can re-embed them surgically.

## Files

| File                      | What it is                                                 |
| ------------------------- | ---------------------------------------------------------- |
| `guard.py`                | `ModelSpec`, `IndexSpec`, `check_query`, `check_upsert`    |
| `worked_example/run.py`   | Six scenarios covering all five verdicts + config errors   |

## Composes with

- `tool-permission-grant-envelope` — wire `check_query`/`check_upsert` as
  the pre-call validator for `embeddings.write` and `vectors.search`
  tools; verdict ≠ `ok` becomes `argument_not_allowed`.
- `structured-error-taxonomy` — `model_id_mismatch` /
  `normalization_mismatch` are `do_not_retry, attribution=local`
  (caller bug); `dim_mismatch` on bulk write with a small `bad`
  list is `retry_failed_only`.
- `embedding-batch-coalescer` — coalesce only after the contract guard
  has passed; you don't want a 100-vector batch to fail half-way because
  one upstream call returned a short vector.
- `embedding-cache-eviction` — the `content_fingerprint` is the right
  cache-key prefix, so swapping models cleanly invalidates the cache
  instead of leaking 1536-dim entries into a 3072-dim world.
- `agent-decision-log-format` — one log line per non-`ok` verdict
  (`{verdict, reason, expected_fp, actual_fp}`) is enough to forensically
  reconstruct *which* model regressed *which* index *when*.

## Worked example output (verbatim)

```
1. ok: matching model
   verdict=ok
   reason: all four contract fields match (fp=4941609016ce)
   fingerprints: expected=4941609016ce actual=4941609016ce

2. model_id_mismatch: someone swapped to embedder-v3 silently
   verdict=model_id_mismatch
   reason: index 'docs-prod-v2' expects model 'embedder-v2', got 'embedder-v3'
   fingerprints: expected=4941609016ce actual=3800a3bcab11

3. dim_mismatch: same model name, but a 'large' variant returns 3072 dims
   verdict=dim_mismatch
   reason: index 'docs-prod-v2' dim=1536, model 'embedder-v2' dim=3072
   fingerprints: expected=4941609016ce actual=50fa1e3a1e69

4. metric_mismatch: dims match but the index was cosine, query is dot
   verdict=metric_mismatch
   reason: index metric=cosine, model metric=dot (dims match but recall will be silently degraded)
   fingerprints: expected=4941609016ce actual=ef20fa522b12

5. normalization_mismatch: index normalized, model returns un-normalized
   verdict=normalization_mismatch
   reason: index normalize=True, model normalize=False (cosine math assumes one or the other; mixing silently shifts the score distribution)
   fingerprints: expected=4941609016ce actual=76174f21b7a2

6. upsert: contract ok, but two of five vectors have wrong dim
   verdict=dim_mismatch
   reason: 2 vector(s) of wrong dim in batch (expected 1536); indices: [2, 4]
   fingerprints: expected=4941609016ce actual=4941609016ce
   rejected indices: [2, 4]

7. construction errors are loud (not silent defaults)
   ModelSpec(dim=0) raised: dim must be > 0, got 0
   IndexSpec(metric='manhattan') raised: metric must be one of ('cosine', 'dot', 'l2'), got 'manhattan'

invariants ok: fingerprint deterministic; normalize-flip changes fingerprint
```

Reproduce: `python3 worked_example/run.py` from this directory.

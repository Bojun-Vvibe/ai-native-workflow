# embedding-staleness-detector-by-mtime

Pure stdlib detector that flags stale entries in an embedding cache by comparing each cached entry's `embedded_at` timestamp against the source file's current mtime, with a deferred-hash escape hatch so a corpus scan stays O(N) stat()s instead of O(N · filesize) rehash.

## Problem

Embedding caches drift silently. The expensive thing was the remote `embed()` call; the entry stores `(source_path, content_hash, embedded_at, embedding_model, vector_dim)` plus a vector. Three bug classes appear in production:

1. **Content actually changed** — file edited after embed. Nearest-neighbor query returns the *old* vector, RAG answers cite stale text, no error.
2. **Touched, not edited** — `git checkout`, `chmod`, `touch`, container-rebuild — mtime advanced, content identical. A naive "re-embed if mtime changed" policy will burn API budget on a no-op.
3. **Source deleted** — file removed, embedding dangling. NN query returns a hit pointing to a path that 404s.

A naive corpus rescan that re-hashes every source file is O(N · filesize). On a million-file corpus that's gigabytes of disk read every scan. mtime is a single `stat()` per file — answers "did anything *possibly* change?" — and the detector only rehashes the candidates mtime flagged.

## When to use

- Any RAG / similarity / agent-memory system with a persistent embedding cache backed by source files (code, docs, transcripts) on disk.
- Run as a periodic compaction pass before a query batch, or in a pre-flight scan when the cache is loaded.
- Pair with `embedding-cache-eviction` (the `evict` action plugs straight in) and `embedding-batch-coalescer` (the `re_embed` candidates batch into one provider call).

## Design

- **Five-verdict surface** with one stable `action` per verdict:

  | verdict | trigger | action | API cost |
  |---|---|---|---|
  | `fresh` | mtime ≤ embedded_at | `keep` | none |
  | `mtime_only` | mtime > embedded_at, hash matches | `refresh_embedded_at` | **none** (just touch the metadata) |
  | `mtime_drift` | mtime > embedded_at, hash differs | `re_embed` | one `embed()` call |
  | `missing` | file does not exist on disk | `evict` | none |
  | `hash_unknown` | mtime > embedded_at, hash deferred | `hash_then_recheck` | none (caller now hashes) |

- **Two-pass scan**: pass 1 is `stat()`-only (no file reads). Files whose mtime advanced are returned `hash_unknown`. Pass 2 hashes only those candidates and re-evaluates. The bulk of a million-file corpus that hasn't changed never gets read off disk.

- **mtime tie-break**: `mtime == embedded_at` is treated as `fresh`, not stale. Filesystem mtime resolution can be 1s on some FSes; an embed pipeline that sets `embedded_at = stat.st_mtime` would otherwise self-flag every entry it just wrote.

- **Decision is pure**: `evaluate(entry: CacheEntry, facts: FsFacts) -> StalenessReport` takes a value-object snapshot of filesystem state and returns a verdict. No `os.stat` inside. The I/O wrapper `scan_entries(...)` is small and isolates the disk surface so the engine can be tested deterministically against synthetic `FsFacts`.

- **`mtime_only` is the cheap-recovery verdict** that the naive design misses entirely. A repo re-checkout touches every file's mtime without changing content; without this verdict the detector would re-embed the entire corpus on every CI run. The action is `refresh_embedded_at` — bump the metadata, keep the vector, no API call.

## Files

- `detector.py` — `CacheEntry`, `FsFacts`, `StalenessReport`, pure `evaluate()`, plus thin `stat_facts()` / `hash_file()` / `scan_entries()` I/O helpers. Stdlib only (`hashlib`, `os`, `dataclasses`).
- `example.py` — two-part worked example: synthetic-fixture pass exercising every verdict, then a real-disk pass against a five-file temp corpus mutated five different ways.

## Worked example output

Captured by running `python3 templates/embedding-staleness-detector-by-mtime/example.py`:

```
============================================================
PART A: synthetic FsFacts (no disk) — engine surface check
============================================================
--- expected 'fresh' ---
  path:    a.txt
  verdict: fresh
  action:  keep
  delta_s: 1.000
  embedded_at: 1000.000
  mtime: 999.000

--- expected 'fresh' ---
  path:    a-tie.txt
  verdict: fresh
  action:  keep
  delta_s: 0.000
  embedded_at: 1000.000
  mtime: 1000.000

--- expected 'mtime_only' ---
  path:    b.txt
  verdict: mtime_only
  action:  refresh_embedded_at
  content_hash: h_b
  delta_s: 500.000
  embedded_at: 1000.000
  mtime: 1500.000

--- expected 'mtime_drift' ---
  path:    c.txt
  verdict: mtime_drift
  action:  re_embed
  delta_s: 500.000
  embedded_at: 1000.000
  mtime: 1500.000
  new_hash: h_c_NEW
  old_hash: h_c

--- expected 'missing' ---
  path:    d.txt
  verdict: missing
  action:  evict
  reason: source_not_on_disk

--- expected 'hash_unknown' ---
  path:    e.txt
  verdict: hash_unknown
  action:  hash_then_recheck
  delta_s: 500.000
  embedded_at: 1000.000
  hint: mtime advanced; re-hash on disk and call evaluate() again
  mtime: 1500.000

invariant: every verdict maps to exactly one action (passes)

============================================================
PART B: real disk — five-file corpus, scanned twice
============================================================
--- Pass 1: stat-only (no file reads) ---
fresh.txt            -> fresh         action=keep
touched.txt          -> hash_unknown  action=hash_then_recheck
edited.txt           -> hash_unknown  action=hash_then_recheck
deleted.txt          -> missing       action=evict
deferred.txt         -> hash_unknown  action=hash_then_recheck

--- Pass 2: re-hash candidates flagged hash_unknown ---
touched.txt          -> mtime_only    action=refresh_embedded_at
edited.txt           -> mtime_drift   action=re_embed
deferred.txt         -> mtime_drift   action=re_embed

--- Final verdict per file (pass2 wins where present) ---
deferred.txt         verdict=mtime_drift   action=re_embed
deleted.txt          verdict=missing       action=evict
edited.txt           verdict=mtime_drift   action=re_embed
fresh.txt            verdict=fresh         action=keep
touched.txt          verdict=mtime_only    action=refresh_embedded_at

invariant: every file landed in its expected verdict (passes)
```

Note the disk pass: of 5 files, only **3** got hashed (the mtime-advanced candidates) and only **2** of those triggered an actual `re_embed`. The naive policy "rehash everything" would have read all 5 off disk; the naive policy "re-embed if mtime changed" would have burned an API call on `touched.txt` for zero benefit. This template avoids both.

## Composes with

- `embedding-cache-eviction` — the `evict` action for `missing` entries plugs into the eviction queue directly. The `evicted_reason` enum extends naturally with `source_not_on_disk`.
- `embedding-batch-coalescer` — collect all `re_embed` candidates from a scan and dispatch them as one batched provider call. The detector returns them in input order, so caller can preserve a stable batch sequence for replay.
- `embedding-dimension-mismatch-guard` — run dimension-guard on `re_embed` outputs; staleness scan finds the candidate, dimension guard validates the new vector before write-back.
- `agent-decision-log-format` — every verdict produces a stable `(verdict, action, source_path)` tuple shaped for one log line per cache entry, queryable by `verdict=mtime_drift` to track corpus churn rate over time.

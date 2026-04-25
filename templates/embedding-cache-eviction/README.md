# embedding-cache-eviction

A small, deterministic cache for embedding vectors that combines **LRU**
recency, **TTL** expiry, and a hard **size cap** — the three policies
that real agent loops actually need together.

## What

`EmbeddingCache(max_entries, ttl_seconds=None)`:

- `get(key)` — vector or `None`. A hit refreshes recency. An expired
  entry is removed and counted as a miss + expiration.
- `put(key, vector)` — insert/update. Sweeps expired entries first,
  then evicts LRU until `len <= max_entries`.
- `stats()` — observability counters: `hits`, `misses`, `expirations`,
  `evictions`, `hit_ratio`, `size`.

The clock is injectable, so the policy is fully testable without
sleeping in tests.

## Why

A naive `dict` cache for embeddings:

- Leaks memory in long-running agents.
- Keeps stale vectors after the underlying model/version changes.
- Has no observability — you can't tell if it's helping.

Pure LRU forgets the "old but cold" problem (a hot key that's actually
stale). Pure TTL evicts hot keys mid-conversation. The combination is
what production agents end up writing anyway; this template makes it
explicit and testable.

## When to use it

- You embed user messages, retrieved chunks, or tool outputs inside an
  agent loop and the same text appears more than once per session.
- You want a bounded memory footprint with predictable eviction.
- You want hit-ratio metrics so you can decide whether the cache is
  worth keeping.

## When NOT to use it

- Distributed workers — this is in-process only. Front it with Redis
  or a shared store if you need cross-process sharing.
- Embeddings whose semantic meaning depends on context window state —
  cache by `(text, model_version, normalization_rules)` tuple, not
  raw text.

## Contract & edge cases

- `max_entries <= 0` → `ValueError`. Don't construct the cache if you
  want it disabled.
- `ttl_seconds=None` → pure LRU, no expiration sweep.
- Re-`put` of an existing key updates the vector and refreshes recency
  but is **not** counted as a hit.
- Eviction is deterministic for a given access sequence and clock —
  good for snapshot tests.

## Worked example output

```
step | action | key                   | result
-----+--------+-----------------------+--------
t=0  |        | hello world           | miss -> embed   (len=4)
t=1  |        | hello world           | hit  -> reuse   (len=4)
t=2  |        | agent loop            | miss -> embed   (len=4)
t=3  |        | tool call             | miss -> embed   (len=4)
t=4  |        | structured output     | miss -> embed   (len=4)
t=5  |        | hello world           | miss -> embed   (len=4)
t=15 |        | agent loop            | miss -> embed   (len=4)
t=16 |        | tool call             | miss -> embed   (len=4)
t=17 |        | tool call             | hit  -> reuse   (len=4)

final stats:
  size          = 2
  max_entries   = 3
  hits          = 2
  misses        = 7
  expirations   = 3
  evictions     = 2
  hit_ratio     = 0.2222222222222222
```

Note how `t=5` is a miss (LRU evicted "hello world" at `t=4`) and
`t=15`/`t=16` are misses because the 10-second TTL elapsed. The cache
ends with two live entries even though `max_entries=3`, because TTL
sweeps ran on insert.

## Running

```bash
python3 worked_example.py
```

Stdlib only. No dependencies.

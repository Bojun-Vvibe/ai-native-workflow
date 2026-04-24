# `tool-result-cache`

Content-addressed result cache for **deterministic** tool calls. The
host hashes `(tool_name, canonical(identity_args))` to produce a key,
and serves a previously-computed result on subsequent calls until the
entry's per-entry `ttl_s` expires.

This is the *positive* sibling of `tool-call-deduplication`:

|  | `tool-call-deduplication` | `tool-result-cache` (this) |
|---|---|---|
| Designed for | Agent loops re-issuing the same call within seconds | Genuinely re-usable results across unrelated callers and across restarts |
| TTL | Single shared `window_seconds` | Per-entry `ttl_s` chosen by the writer |
| Safety opt-in | None — caller responsibility | **Mandatory** — tool must be in `safe_tools` or write raises `UnsafeCacheError` |
| Negative caching | No | No (errors are never cached, by design) |
| Persistable | No (in-memory thought-loop killer) | Yes (`state()` snapshot is JSON-serializable) |

Use both. Dedup absorbs short-window thought loops cheaply; this cache
serves slow deterministic calls (`sha256_of_file`, `parse_ast`,
`embed_text` with a fixed model) across the lifetime of the host.

## Why a mandatory safe-list

The most common production accident is caching the result of a tool
that *looks* deterministic but isn't:

- `read_clock(tz="UTC")` → returns "now"
- `list_files(dir="/srv")` → directory mutates
- `web_fetch(url=...)` → page mutates
- `random_seed()` → not even a question

Every one of these has been cached in the wild and produced a stale
result that survived the bug fix because the cache outlived the
process. The remedy is to **require** an explicit allowlist:
`ToolResultCache(safe_tools=frozenset({"sha256_of_file"}), ...)`.
Writes for any tool outside the set raise `UnsafeCacheError` and are
counted in `state.refused_unsafe_writes`.

## SPEC

### `cache_key(tool_name, args, identity_fields=None) -> str`

Returns a 64-char hex SHA-256. If `identity_fields` is `None`, all args
participate. Otherwise only the listed keys (silently dropped if
absent — useful for optional args).

Floats anywhere in identity-args raise `CacheKeyError` with a JSON
pointer to the offending field; same trap, same fix as in
`tool-call-deduplication` (use ints or string-encode).

### `ToolResultCache(safe_tools, now_fn)`

Inject `now_fn` (`time.monotonic` in production, a fake clock in tests)
so the cache is fully deterministic.

| Method | Behavior |
|---|---|
| `lookup(key)` | Returns `{result, written_at, expires_at, source_call_id}` or `None`. Lazily evicts an expired entry first. |
| `write(tool_name, key, result, ttl_s, source_call_id)` | Stores a result. Raises `UnsafeCacheError` if `tool_name not in safe_tools`. Raises `ValueError` if `ttl_s <= 0`. |
| `state()` | Sorted-key snapshot: `entries`, `hits`, `misses`, `evictions`, `refused_unsafe_writes`, `safe_tools`. |

Keep `source_call_id` in your trace — when a downstream consumer asks
"why did call X return Y?" the answer is "served from cache, original
producer was call `source_call_id`."

## Invariants

1. Two calls with byte-identical canonicalized identity-args produce
   the same key.
2. Dict key order does NOT affect the key.
3. Floats in identity-args raise `CacheKeyError`.
4. `lookup` after `expires_at` returns `None` and increments `evictions`.
5. `write` for a tool not in `safe_tools` raises and increments
   `refused_unsafe_writes` — the cache is unchanged.
6. `lookup` never mutates an entry's `expires_at` (no read-extends-TTL
   behavior; that turns a cache into a leak).

## Files

- `cache.py` — pure stdlib reference engine.
- `example.py` — three-part worked example.
- `expected_output.txt` — captured stdout (also pasted below).

## Worked example output — `example.py`

```
== part 1: deterministic tool, identity_fields filters volatile metadata ==
key(args_a) == key(args_b)? True  (volatile request_id ignored)
key(args_a) == key(args_c)? False  (path differs -> different key)
call-A lookup: miss; executing tool, writing result
call-B lookup (volatile-only diff): HIT source_call_id=call-A written_at=1000.00
           result.bytes=4096

== part 2: non-deterministic tool refuses to cache ==
UnsafeCacheError raised as expected: refusing to cache non-deterministic tool 'read_clock'; add it to safe_tools to opt in

== part 3: per-entry TTL expires ==
lookup at t=1004.95 (within ttl): HIT
lookup at t=1005.55 (past ttl):   miss (evicted)

final state: entries=1 hits=2 misses=2 evictions=1 refused_unsafe_writes=1
safe_tools: ['read_file', 'sha256_of_file']
```

Things to notice:

- `args_a` and `args_b` differ only in `request_id` and dict key order.
  Because `identity_fields=["path"]` is declared, both hash the same
  and `call-B` is a HIT carrying `source_call_id=call-A`.
- `args_c` has a different `path` so it keys differently — no false
  positives across logically-different calls.
- The `read_clock` write attempt is refused loudly, not silently
  dropped: `state.refused_unsafe_writes=1` so a CI gate can catch
  callers who try to opt in the wrong tools.
- TTL is per-entry: the `read_file` entry was written with `ttl_s=5.0`
  and is evicted between `t=1004.95` (HIT) and `t=1005.55` (miss),
  bumping `state.evictions` from 0 to 1.
- `state.hits=2` because `call-B` and the within-TTL `read_file`
  lookup both hit; `state.misses=2` because `call-A` and the past-TTL
  `read_file` lookup both missed.

## Composition

- **`tool-call-deduplication`** — in-process thought-loop killer. Run
  dedup *first* (cheap, no allowlist), then this cache (mandatory
  allowlist, longer-lived). A dedup hit short-circuits before this
  cache is even consulted.
- **`structured-error-taxonomy`** — never cache an error result. The
  caller must classify the result as a success before calling `write`.
- **`agent-decision-log-format`** — log every HIT with
  `source_call_id` so the audit trail can prove which producer's
  result was served.
- **`tool-permission-grant-envelope`** — the cache lookup happens
  AFTER the grant decision. A denied call must never reach `write`
  (and won't — the caller never gets a result to cache).

## Non-goals

- Negative caching (failed calls are not cached; failures are
  re-executed by design).
- Cross-process persistence (snapshot+reload via `state()` is the
  caller's job; the engine itself is in-memory).
- Read-extends-TTL semantics (a cache that refreshes on read is a
  memory leak in disguise).
- Stampede control (if 50 callers miss the same key simultaneously,
  all 50 will execute; add a per-key in-flight lock at the call site
  if you need single-flight).

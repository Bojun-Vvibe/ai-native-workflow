# `tool-call-deduplication`

In-process deduplication of agent tool calls by **call-signature
hash**. When an agent loops and re-issues the same logical call within
a short window, the host returns the previously cached result instead
of re-executing the side effect.

This is the *signature-based* sibling of `tool-call-retry-envelope`'s
explicit idempotency key:

|  | `tool-call-retry-envelope` | `tool-call-deduplication` (this) |
|---|---|---|
| Caller mints a key? | Yes (`idempotency_key`) | No |
| Storage | SQLite, cross-process | In-memory, per-process |
| Designed for | At-least-once transport, host crashes | Agents that re-issue the same call within seconds |
| Key derivation | Caller-controlled | Hash of `(tool_name, canonical(identity_args))` |
| Cross-restart safe | Yes | No |

Both can be used together. The retry envelope catches the
"transport-blip retried the same wire request" case; this template
catches the "agent thought-loop re-asked the same question" case.

## Why hash-based dedup needs care

The naive version (hash the whole args dict) fails the moment any
field is volatile — a `request_id`, a wall-clock timestamp, a
trace-id. Every call hashes differently and dedup never fires.

This template makes that failure mode impossible by:

1. **`identity_fields` allowlist** — caller declares the subset of
   args that determine the *result*. Everything else (timestamps,
   request-ids, freeform notes) is ignored at hash time.
2. **No floats in identity-args** — JSON float round-tripping silently
   loses precision; a `0.1 + 0.2` in one call won't hash like a
   literal `0.3` in another. The canonicalizer raises
   `CanonicalizationError`. Use ints or string-encode.
3. **Canonical JSON** — sorted keys, no whitespace, UTF-8.
   Dict-construction order does not affect the hash.
4. **Lazy expiry on access** — entries past `window_seconds` are
   evicted on the next `lookup` or `state()` so memory does not
   accumulate.

## SPEC

### `dedup_key(tool_name, args, identity_fields=None) -> str`

Returns a 64-char hex SHA-256. If `identity_fields` is `None`, all
args participate. Otherwise only the listed keys (silently dropped if
absent — useful for optional args).

### `DedupCache(window_seconds, now_fn)`

Inject `now_fn` (e.g. `time.monotonic` in production, a fake clock
in tests) so the cache is fully deterministic.

| Method | Behavior |
|---|---|
| `decide(tool_name, args, call_id, identity_fields=None)` | Returns `{"verdict": "execute" \| "use_cached", "key": <hex>, "cached": <envelope or None>}`. |
| `lookup(key)` | Returns the cached envelope or None; evicts expired entries. |
| `record(key, call_id, result)` | Stores a result. Idempotent on `(key, same call_id)`. |
| `state()` | Sorted-key snapshot: `entries`, `evictions`, `hits`, `misses`, `window_seconds`. |

### Cached envelope shape

```python
{"cached_at": float, "original_call_id": str, "result": Any}
```

Keep `original_call_id` in your trace — it's the audit-trail link
showing which prior call produced the served result.

## Invariants

1. Two calls with byte-identical canonicalized identity-args produce
   the same key.
2. Dict key order does NOT affect the key.
3. Floats in identity-args raise `CanonicalizationError`.
4. `lookup` after `window_seconds` returns `None` and evicts the entry.
5. `record(key, same_call_id, ...)` is a no-op (no `cached_at` bump).
6. `record(key, different_call_id, ...)` refreshes `cached_at` and
   `original_call_id` (treats it as a fresh authoritative result).

## Files

- `dedup.py` — pure stdlib reference engine.
- `examples/example_1_agent_loop.py` — agent loops; second call hits cache.
- `examples/example_2_identity_fields_and_expiry.py` — `identity_fields` filters out volatile metadata; window expiry; float rejection.

## Worked example output — `example_1_agent_loop.py`

An agent calls `read_file("/srv/notes/spec.md")` then 50ms later
re-issues the same call (with dict keys in a different order). The
second call is served from cache:

```
t=1000.0 call-001 decision: execute key=79130f436354...
           executed -> {"lines": 142, "path": "/srv/notes/spec.md", "sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}

t=1000.05 call-002 decision: use_cached key=79130f436354...
           served from cache; original_call_id=call-001 cached_at=1000.00
           result={"lines": 142, "path": "/srv/notes/spec.md", "sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}

t=1000.05 call-003 (different path) decision: execute

final state: {"entries": 1, "evictions": 0, "hits": 1, "misses": 2, "window_seconds": 60.0}
```

Things to notice:

- `call-001` and `call-002` produce the *same* key (`79130f436354…`)
  even though the dict literals had different field orders.
- `call-003` (different `path`) keys differently and executes — no
  false positives.
- The cached envelope carries `original_call_id="call-001"` so the
  trace shows the audit link from `call-002 → call-001`.
- `state.misses=2` counts both `call-001` (no prior entry) and
  `call-003` (different key); `state.hits=1` is `call-002`.

## Worked example output — `example_2_identity_fields_and_expiry.py`

```
== part 1: identity_fields filters out volatile metadata ==
key(args_a) == key(args_b)? True  (volatile fields ignored)
key(args_a) == key(args_c)? False  (limit changed -> different key)

call-A: execute
call-B (volatile-only diff): use_cached served-from=call-A

== part 2: window expiry ==
advancing clock by 11s (window=10s)...
call-D after expiry: execute  (entry was evicted)

== part 3: float rejection ==
CanonicalizationError raised as expected: float not allowed in identity-args at $.score: 0.875. Use int or string-encode.

final state: {"entries": 1, "evictions": 1, "hits": 1, "misses": 2, "window_seconds": 10.0}
```

Things to notice:

- `args_a` and `args_b` differ only in `request_id` and `now`;
  declaring `identity_fields=["query","limit"]` makes them hash the
  same. Naive whole-args hashing would have produced two keys and
  zero cache hits.
- After advancing the fake clock past `window_seconds`, the entry is
  evicted *and counted* in `state.evictions=1`, not silently dropped.
- A literal float `0.875` raises `CanonicalizationError` with a JSON
  pointer (`$.score`) so the caller knows exactly which field to
  string-encode.

## Composition

- **`tool-call-retry-envelope`** — the cross-process, caller-keyed
  twin. Use both: this template absorbs in-loop duplicates cheaply;
  the envelope catches transport-replay duplicates across restarts.
- **`agent-decision-log-format`** — log every `verdict=use_cached`
  with `original_call_id` so a downstream auditor can prove the
  served result was identical to the one that ran.
- **`tool-permission-grant-envelope`** — the dedup decision happens
  AFTER the grant decision. A denied call must never be cached
  (and isn't — the caller never reaches `record`).
- **`structured-error-taxonomy`** — never cache an error result;
  classify failures and let the caller retry under the retry envelope.

## Non-goals

- Negative caching (failed calls are not cached; failures are
  re-executed by design).
- Cross-process persistence (use the retry-envelope SQLite table).
- TTL per entry (a single window keeps the API tiny; if you need
  per-entry TTL you've outgrown this template).

# prompt-cache-key-canonicalizer

Deterministic SHA-256 cache keys for prompt-call descriptors. Two
semantically identical calls always produce the same key, regardless of
JSON-key order, float jitter, or tool ordering.

## What it solves

Naive caching by `hash(json.dumps(call))` misses every time because:

- Python `dict` iteration order is insertion-defined; `{"a":1,"b":2}`
  hashes differently from `{"b":2,"a":1}`.
- `0.7` vs `0.7000000001` look different but are semantically the same
  to a temperature setting rounded to 4 decimals upstream.
- The order of tool definitions in a `tools=[...]` list is not
  semantically meaningful but changes the hash.
- Large `context` blobs blow out the cache key length.

This template gives you one function: `canonicalize(desc) -> (json, sha256)`
that handles all of this consistently.

## When to use

- LLM/embedding response caching where you want high hit rate.
- Memoization layer in front of a deterministic-temperature model call.
- Building a content-addressed prompt log.

## When NOT to use

- Caching across schema versions — when descriptor schema changes,
  bump a `cache_namespace` field yourself; this engine doesn't version.
- Authoritative dedup of *outputs* — that's a different hash (hash the
  response, not the request).
- Calls with non-deterministic side-effecting tools — same key, different
  result, you'll serve stale data. Don't cache those at all.

## Files

- `SPEC.md` — canonicalization rules.
- `canon.py` — stdlib-only reference engine + CLI.

## CLI

```
python canon.py < descriptor.json
```

Prints `{"canonical": "<json>", "key": "<sha256>"}`.

## Worked example 1 — equivalence under reordering and float jitter

Two descriptors, same semantics:

```
$ echo '{"model":"m1","temperature":0.7,"prompt":"hi","tools":[{"name":"b","arg":1},{"name":"a","arg":2}]}' | python canon.py
{"canonical": "{\"context_hash\":\"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b\",\"model\":\"m1\",\"prompt\":\"hi\",\"temperature\":0.7,\"tools\":[{\"arg\":2,\"name\":\"a\"},{\"arg\":1,\"name\":\"b\"}]}", "key": "74c8aafd5f334063e3961ac40bfd332a7473e92b66670a7b7b143b0c42c84cfa"}

$ echo '{"prompt":"hi","tools":[{"arg":2,"name":"a"},{"arg":1,"name":"b"}],"temperature":0.7000000001,"model":"m1"}' | python canon.py
{"canonical": "{\"context_hash\":\"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b\",\"model\":\"m1\",\"prompt\":\"hi\",\"temperature\":0.7,\"tools\":[{\"arg\":2,\"name\":\"a\"},{\"arg\":1,\"name\":\"b\"}]}", "key": "74c8aafd5f334063e3961ac40bfd332a7473e92b66670a7b7b143b0c42c84cfa"}
```

Same `key` (`74c8aafd...`). Top-level keys reordered, tools reordered,
temperature differs at the 10th decimal — none of it matters.

## Worked example 2 — context summarization and sensitivity

```
$ echo '{"model":"m1","temperature":0.0,"prompt":"summarize","context":{"docs":["a","b"],"user":"alice"}}' | python canon.py
{"canonical": "{\"context_hash\":\"fa81c2a21eaea1776cf0fa65dc2d570a2ed74f9fcc8be352bb8fe57315b8dc93\",\"model\":\"m1\",\"prompt\":\"summarize\",\"temperature\":0.0}", "key": "2dc587e5357b0c57cba15653ae0b3dc9f32d64307b56a1a113a22b4e0f9a0d66"}

$ echo '{"model":"m1","temperature":0.0,"prompt":"summarize","context":{"user":"alice","docs":["a","b"]}}' | python canon.py
{"canonical": "{\"context_hash\":\"fa81c2a21eaea1776cf0fa65dc2d570a2ed74f9fcc8be352bb8fe57315b8dc93\",\"model\":\"m1\",\"prompt\":\"summarize\",\"temperature\":0.0}", "key": "2dc587e5357b0c57cba15653ae0b3dc9f32d64307b56a1a113a22b4e0f9a0d66"}

$ echo '{"model":"m1","temperature":0.0,"prompt":"summarize","context":{"user":"alice","docs":["a","b","c"]}}' | python canon.py
{"canonical": "{\"context_hash\":\"f97d7d5f6f15a82e01f040ab82e4787030bc90083dc4bedf962322c286d0468f\",\"model\":\"m1\",\"prompt\":\"summarize\",\"temperature\":0.0}", "key": "992013f8ba1608c1e473fd3157df0f28c1b382c87b4b9d76e1b393925a152e7b"}
```

First two: same `context_hash` and same `key` despite reordered context
keys. Third: added one document → context hash changes → outer key
changes.

## Integration sketch

```python
from canon import canonicalize

def cached_call(desc, backend, store):
    _, key = canonicalize(desc)
    if (hit := store.get(key)) is not None:
        return hit
    result = backend(desc)
    store.set(key, result)
    return result
```

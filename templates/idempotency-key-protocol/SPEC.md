# SPEC: idempotency-key-protocol

## Wire format

Every tool call carries an envelope of the form:

```json
{
  "idempotency_key": "<caller-provided opaque string, 1..128 chars>",
  "request": { ... arbitrary tool-specific payload ... },
  "issued_at": "<RFC3339 UTC timestamp>",
  "ttl_seconds": 86400
}
```

Every tool response carries:

```json
{
  "idempotency_key": "<echoed>",
  "status": "fresh" | "replayed" | "conflict",
  "response": { ... tool-specific result, present iff status != conflict ... },
  "stored_at": "<RFC3339 UTC timestamp of the original execution>",
  "conflict_detail": { ... present iff status == conflict ... }
}
```

## The three rules

### Rule 1 — fresh

If the store has no live entry for `idempotency_key`:

1. Execute the tool.
2. Persist `(key, request_hash, response, stored_at)` with TTL.
3. Return `status = "fresh"`.

### Rule 2 — replay

If the store has a live entry for `idempotency_key` AND
`sha256(canonical_json(request)) == stored.request_hash`:

1. **Do not** execute the tool.
2. Return the stored response with `status = "replayed"` and
   `stored_at` set to the original execution time.

### Rule 3 — conflict

If the store has a live entry for `idempotency_key` AND
`sha256(canonical_json(request)) != stored.request_hash`:

1. **Do not** execute the tool.
2. Return `status = "conflict"` with `conflict_detail` containing
   `expected_request_hash`, `received_request_hash`, and
   `stored_at`.
3. The agent SHOULD treat this as a hard error and surface it —
   it indicates a bug in key construction or in request
   determinism, not a transient failure.

## Canonicalization

`canonical_json(x)` MUST produce byte-identical output for
semantically equal inputs. The reference implementation uses:

```python
json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

Callers MUST NOT include wall-clock timestamps, randomly sampled
fields, or other non-deterministic content in the `request`
payload. If they do, every retry is a conflict.

## TTL semantics

- TTL is set at first write; subsequent replays do **not** extend
  it. A long-running mission that wants to dedupe across hours
  must pick a TTL that covers its longest expected retry window.
- Expired entries are treated as absent: the next call with the
  same key falls through to Rule 1.

## What the store does NOT do

- It does not generate keys. Caller-only.
- It does not retry on its own. That is the retry envelope's job.
- It does not cap concurrency. Two simultaneous calls with the
  same key on a fresh entry race; the loser sees Rule 2 on its
  second attempt. Callers needing strict single-flight should add
  a per-key lock at a higher layer.
- It does not validate the response shape. The response is opaque
  bytes from the store's perspective.

# tool-call-idempotency-key

## Problem

Many "tools" an agent calls have side effects: create-ticket, send-email, charge-card, post-message. When a network glitch or agent retry causes the *same logical operation* to be invoked twice, you get duplicate tickets, duplicate emails, double charges. The agent's retry envelope alone cannot solve this — the tool itself must dedup.

## When to use

- Wrapping any **non-idempotent** tool the agent can invoke.
- You can have the *caller* generate a stable per-operation key (e.g. derived from the user message id, the plan step id, or `uuid4()` chosen once at plan time and reused on retry).
- You want a loud failure when the same key is reused with different args (almost always a bug).

## When NOT to use

- The tool is already truly idempotent (`PUT /resource/{id}` with the same body). Wrapping adds no value.
- You need cross-process / cross-host dedup. This template is single-process. For distributed dedup back it with Redis / a database row with a unique constraint on the key.
- The "same key" semantics differ across attempts (e.g. retries with intentionally different args). Use a different correlation primitive instead.

## API sketch

```python
from template import IdempotencyCache, with_idempotency

cache = IdempotencyCache(ttl_seconds=300)

def real_create_ticket(title, priority="p2"): ...

create_ticket = with_idempotency(cache, real_create_ticket)

# First call: actually invokes real_create_ticket.
t = create_ticket("disk full", priority="p1", idempotency_key="plan-step-42")
# Retry (network blip): replays cached result, real tool not called again.
t2 = create_ticket("disk full", priority="p1", idempotency_key="plan-step-42")
assert t == t2
```

Three failure signals it surfaces, all loud:

| situation | result |
| --- | --- |
| same key + same args, within TTL | replay cached result (or re-raise cached exception) |
| same key + different args | `IdempotencyKeyConflict` raised — almost certainly a client bug |
| same key while original still running | `IdempotencyKeyInFlight` raised — caller decides wait/abort |
| key not seen, or expired past TTL | tool is invoked normally |

## Worked example invocation

```
python3 templates/tool-call-idempotency-key/worked_example.py
```

## Worked example output

```
=== first call (miss) ===
  result={'ticket_id': 'T-0001', 'title': 'disk full on host-7', 'priority': 'p1'}  underlying_calls=1
=== retry within TTL, same key + args (hit, replay) ===
  result={'ticket_id': 'T-0001', 'title': 'disk full on host-7', 'priority': 'p1'}  underlying_calls=1
=== different key, same args (miss, fires again) ===
  result={'ticket_id': 'T-0002', 'title': 'disk full on host-7', 'priority': 'p1'}  underlying_calls=2
=== same key, different args (conflict raised) ===
  raised: idempotency key 'op-abc' reused with different arguments
=== TTL expiry: same key fires fresh after window ===
  result={'ticket_id': 'T-0003', 'title': 'disk full on host-7', 'priority': 'p1'}  underlying_calls=3
=== in-flight detection ===
  out=70  status_seen_during_call=['in_flight']
  reserved-with-other-args -> conflict: idempotency key 'k2' reused with different arguments
  reserved-same-args -> in-flight: idempotency key 'k3' is still in flight
all assertions passed
```

## Design notes

- **Args canonicalization**: `json.dumps(..., sort_keys=True, separators=(',',':'), default=str)` then sha256. Stable across dict insertion order; `default=str` lets non-JSON objects (datetimes, paths) participate predictably without crashing.
- **Cached exceptions**: a tool that raised once on a key will re-raise the same exception type/message on replay until TTL. This is the right default — retries should not silently flip a "permanent" error into a success.
- **GC**: every `get` triggers a sweep of expired entries plus an oldest-completed eviction if `max_entries` is exceeded. Cheap; no background thread.
- **Thread-safety**: deliberately not built in. Wrap with your own lock if needed, or back the cache with a real KV store.

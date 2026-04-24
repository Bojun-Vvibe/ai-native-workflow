# Example 01 — replay deduped

A `create_branch` tool call carries an idempotency key. The agent's
retry envelope fires three times (perhaps the response packet was
dropped twice). The protocol guarantees the underlying side effect
runs exactly once.

## Run

```
python3 run.py
```

## Actual stdout

```
# Three retries with the same key + body:
attempt=1 status=fresh branch=fix/cache-eviction
attempt=2 status=replayed branch=fix/cache-eviction
attempt=3 status=replayed branch=fix/cache-eviction
# Underlying side effect ran 1 time(s): ['fix/cache-eviction']
```

## What to notice

- `attempt=1` returns `status=fresh` — the tool actually ran.
- `attempt=2` and `attempt=3` return `status=replayed` with the
  identical response. The branch list at the end confirms the
  side effect did not repeat.
- The clock is injected (a deterministic counter), so this example
  produces byte-identical output across runs.

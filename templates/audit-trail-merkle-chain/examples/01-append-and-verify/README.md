# Example 01 — append and verify

Append four agent decisions to a fresh chain, publish the head
hash, then verify the chain end-to-end against that published
head.

## Run

```
python3 run.py
```

## Actual stdout

```
appended index=0 entry_hash=e13917e39dd99045
appended index=1 entry_hash=af348003a469b3f2
appended index=2 entry_hash=436f7a55ab0be78a
appended index=3 entry_hash=55fd8b793ec06ecf
published_head=55fd8b793ec06ecf
verify ok=True entries=4 head=55fd8b793ec06ecf
```

## What to notice

- Each `entry_hash` is fully determined by `index`, `ts`,
  `prev_hash`, and `payload`. The clock is injected, so this run
  is byte-identical across machines.
- `published_head` matches the final `entry_hash`. In a real
  deployment this is the value the operator pins outside the log
  file (chat pin, signed snapshot, etc.).
- Verification reports `ok=True` and confirms the recomputed
  head matches the published one.

# Example 02 — tamper detected

Append five entries, snapshot a clean verification, then edit one
byte at line index 2 (changing `"review"` to `"rEview"`). Re-verify
and watch the chain break at the exact tampered index.

## Run

```
python3 run.py
```

## Actual stdout

```
clean ok=True entries=5 head=d83cda9d93f7bd1d
tampered: replaced 'review' with 'rEview' at line index 2
tampered ok=False broken_at_index=2 reason=entry_hash_mismatch
```

## What to notice

- The clean verification accepts the chain and matches the
  published head.
- A single-character edit at line 2 produces
  `entry_hash_mismatch` *at index 2* — the verifier points at the
  exact entry that was modified, not somewhere downstream.
- If the tampered entry weren't the one whose stored hash got
  recomputed-and-broken, the chain would have failed at the
  *next* line with `prev_hash_mismatch` instead. Either way, the
  tamper is localised and announced.
- Detection here only works because the original head hash was
  captured *before* the tamper. If the attacker also controls the
  published head, this entire mechanism collapses — see the
  "Head-hash publication" section in the parent README.

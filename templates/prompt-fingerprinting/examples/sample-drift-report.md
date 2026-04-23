# Sample drift report — v1 → v2

```
DRIFT DETECTED
  model: unchanged
  provider: unchanged
* system_prompt: len 276 → 329 (+53); hash changed
* tools: reordered (no schema change in name set): ['read', 'write', 'edit', 'bash', 'grep', 'glob'] → ['bash', 'read', 'write', 'edit', 'grep', 'glob']
  decoding: unchanged

  cache_hash:    30cf6eb66756 → 490bdb078dc1   (cache prefix BROKEN — full re-prime expected)
  semantic_hash: 7e2a95d716f4 → 59bfa1e44528   (intent CHANGED)

  verdict: intentional_change
```

## Reading this report

- The system prompt grew by 53 characters: someone added a "remember
  to check git status" line. This is a real intent change
  (`semantic_hash` flipped) so it's classified as `intentional_change`,
  not `silent_cache_break`.
- Tools were also reordered (`bash` floated to the front). This
  alone would not change `semantic_hash`, but combined with the
  prompt change it ships as part of the same drift.
- `cache_hash` flipped: the next session will re-prime the cache
  from scratch. Expect a 5–15× cost spike on the *first* turn of
  the next mission run, then back to baseline.

## What you'd do next

1. If you only meant to add the rule, revert the tool reorder.
2. Re-fingerprint and confirm `cache_hash` matches v1 except for
   the system-prompt component.
3. Land the change once during a low-traffic window so the re-prime
   cost is incurred once, not per active session.

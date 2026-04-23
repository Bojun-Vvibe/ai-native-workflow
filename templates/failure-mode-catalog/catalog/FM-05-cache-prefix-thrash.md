# FM-05 — Cache Prefix Thrash

**Severity:** costly
**First observed:** as soon as we tracked cache hit rate
**Frequency in our ops:** weekly (and almost always invisible
without instrumentation)

## Diagnosis

A small change at the front of the prompt — a reordered tool, a
whitespace edit, a system-prompt rule addition — invalidates the
provider's prompt cache. The next session pays full price for
re-priming the prefix. If the change happens silently (someone
edited a config without realizing it shifted the prefix), the
cost regression is invisible until you read the bill.

## Observable symptoms

- `cache_hit_rate` drops from a baseline (e.g., 0.75) to near
  zero across all sessions on the same day.
- First-turn token-in count rises sharply; subsequent turns
  return to baseline.
- Total daily cost jumps with no change in mission count or
  shape.
- Bill goes up the day after a small "cleanup" PR landed in the
  prompt repo.

## Mitigations

1. **Primary** — use [`prompt-fingerprinting`](../../prompt-fingerprinting/)
   to detect drift; gate prompt-changing PRs on a fingerprint
   diff in CI.
2. **Secondary** — adopt the discipline in
   [`prompt-cache-discipline-system-prompt`](../../prompt-cache-discipline-system-prompt/)
   (stable prefix, append-only history, cache-aware tool defs)
   and pair with [`cache-aware-prompt`](../../cache-aware-prompt/)
   for SDK-level breakpoints.

## Related

FM-01 (Context Rot — distinct, but both produce mysterious cost
spikes).

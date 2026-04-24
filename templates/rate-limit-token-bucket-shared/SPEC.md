# SPEC: shared token bucket

## State file format (JSON)

```
{
  "capacity": <int>,        # max tokens
  "refill_per_sec": <float>,# tokens added per second
  "tokens": <float>,        # current tokens (fractional ok)
  "last_refill_ns": <int>   # monotonic-ish wall ns of last refill
}
```

## Algorithm

`acquire(n, now_ns)`:

1. Open state file with `fcntl.flock(LOCK_EX)`.
2. Read JSON; if missing, init to full bucket with `last_refill_ns=now_ns`.
3. `elapsed_s = max(0, (now_ns - last_refill_ns) / 1e9)`.
4. `tokens = min(capacity, tokens + elapsed_s * refill_per_sec)`.
5. `last_refill_ns = now_ns`.
6. If `tokens >= n`: subtract `n`, write back, return `(True, 0.0)`.
7. Else: compute `wait_s = (n - tokens) / refill_per_sec`, write back (no subtract), return `(False, wait_s)`.

## Determinism

The engine accepts an injected `now_ns` so tests are deterministic. Production
callers pass `time.monotonic_ns()`.

## Concurrency

`fcntl.flock` is process-wide on POSIX. Multiple worker processes pointing at
the same state file see linearised acquires. No partial writes: write to
`<file>.tmp` then `os.replace`.

## Non-goals

- No cluster-wide coordination (single host filesystem only).
- No fairness across callers (FIFO not guaranteed).
- No async API (synchronous blocking only).

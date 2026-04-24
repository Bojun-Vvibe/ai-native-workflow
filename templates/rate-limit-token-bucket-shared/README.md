# rate-limit-token-bucket-shared

A multi-process coordinated token-bucket rate limiter backed by a single
JSON state file with `fcntl` exclusive locking. Prevents fleet stampede
when N worker processes on the same host call the same upstream API.

## What it solves

You run K parallel agent workers that hit the same external API with a
1000 req/min ceiling. Each worker's in-memory limiter has no idea what
the other workers consumed. Within seconds you trip the upstream limit
and everyone backs off chaotically.

This template gives all workers a **single shared bucket** they atomically
debit through a file lock, so the fleet-wide rate stays under the cap.

## When to use

- Multiple processes on one host sharing a quota.
- You want zero infrastructure (no Redis, no daemon).
- Determinism matters — you can inject `now_ns` for tests.
- Rate ≤ a few thousand acquires/sec (file lock is the bottleneck).

## When NOT to use

- Multi-host coordination — file locks don't cross machines. Use Redis.
- Sub-millisecond latency budgets — `flock` adds ~50–500us per call.
- You need fairness/FIFO across callers — this is best-effort.
- Async event loops — the API is blocking. Wrap it in `run_in_executor`.

## Files

- `SPEC.md` — state schema and algorithm.
- `bucket.py` — stdlib-only reference engine + CLI.

## CLI

```
python bucket.py init    <state_file> <capacity> <refill_per_sec>
python bucket.py acquire <state_file> <n> [--now-ns N]
python bucket.py peek    <state_file>     [--now-ns N]
```

`acquire` exits 0 on success, 2 on insufficient tokens (caller should sleep
`wait_s` seconds and retry).

## Worked example 1 — basic refill denial

```
$ python bucket.py init /tmp/bk.json 5 2.0 --now-ns 1000000000
{"initialized": true, "tokens": 5.0}

$ python bucket.py acquire /tmp/bk.json 3 --now-ns 1000000000
{"ok": true, "tokens_left": 2.0, "wait_s": 0.0}

$ python bucket.py acquire /tmp/bk.json 3 --now-ns 1000000000
{"ok": false, "tokens_left": 2.0, "wait_s": 0.5}
```

At t=1s we have 5 tokens. First acquire takes 3 → 2 left. Second acquire
needs 3 but bucket has 2 → denied. Refill rate is 2 tok/s, so caller is
told to wait 0.5s for the missing 1 token.

## Worked example 2 — refill across calls and cap clamp

```
$ python bucket.py init /tmp/bk2.json 10 5.0 --now-ns 0
{"initialized": true, "tokens": 10.0}

$ python bucket.py acquire /tmp/bk2.json 10 --now-ns 0
{"ok": true, "tokens_left": 0.0, "wait_s": 0.0}

$ python bucket.py acquire /tmp/bk2.json 4 --now-ns 1000000000
{"ok": true, "tokens_left": 1.0, "wait_s": 0.0}

$ python bucket.py peek /tmp/bk2.json --now-ns 2000000000
{"tokens": 6.0}
```

After draining at t=0, 1 second later 5 tokens have refilled (rate
5/s). Acquire 4, leaving 1. At t=2s another 5 would refill (1 + 5 = 6),
well below the cap of 10. `peek` does not consume — it just reports.

## Integration sketch

```python
from bucket import acquire
import time

def call_api():
    while True:
        ok, wait_s, _ = acquire("/var/run/myapp/upstream.bucket", 1, time.monotonic_ns())
        if ok:
            return real_http_call()
        time.sleep(wait_s)
```

Initialize the state file once at deploy time; let workers race on it.

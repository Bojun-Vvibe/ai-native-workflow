# tool-call-batching-window

Debounce-style batching window that collapses N small tool calls
issued within a short interval into one bulk call.

## Why this exists

Many tool surfaces have a *bulk* form whose cost (round-trip latency,
billing unit, rate-limit token) is roughly the same as the single-item
form:

- `read_files([…])` vs N × `read_file`
- `vector_lookup_batch([…])` vs N × `vector_lookup`
- `db.executemany(stmt, rows)` vs N × `db.execute(stmt, row)`

When an agent loop emits a burst of small calls (e.g. "read these 12
files I just discovered"), paying 12 round-trip costs is strictly
worse than paying one bulk-call cost — *provided the caller can
tolerate a small wait*. This template is the small piece of glue that
enables that swap without forcing the agent to know about batching.

## What it guarantees

| Rule | Why |
|---|---|
| **Two flush triggers, OR-ed.** Size cap (`max_batch_size`) trips immediately on `submit`; deadline (`max_wait_s`) trips on the next `tick`. Whichever fires first wins. | Either bound makes throughput predictable; together they cover both bursty and sparse arrival patterns. |
| **Deadline measured from the *first* item**, not the most recent. | A trickle of one item every (max_wait_s − ε) must NOT defer the flush forever. This is the bug almost every naive debouncer has. |
| **Order preservation.** `bulk_fn` receives args in submit-order; results map back by index. | A `bulk_fn` that returns the wrong-length list raises `BatchSizeMismatch` — a loud failure, not a silent misattribution. |
| **`bulk_fn` errors fan out.** If the bulk call raises, every pending handle in that flush is resolved with the same exception. | Per-call retry policy lives in the *caller* (compose with `tool-call-retry-envelope`), not in the batcher. |
| **No background threads, no asyncio.** Pure value-object. Caller drives time via `tick(now_s)` (loop, frame, heartbeat). | Deterministic. Testable with an injected clock. Framework-agnostic. |
| **`flush()` drains synchronously**, even mid-window. | Useful in shutdown paths and inside `streaming-cancellation-token` cleanups. |
| **No partial flushes.** A flush is all-or-nothing across the pending list. | Avoids the "which 3 of 5 already went?" bookkeeping nightmare. |
| **`close()`** drains and refuses further `submit`. | Clean shutdown without leaking pending items. |

## When NOT to use this

- **Latency-critical interactive calls** (a UI typing-completion call):
  any wait-window is felt by the user. Batch upstream in the agent
  loop, not at the I/O boundary.
- **Calls with side-effect ordering across keys** (e.g. write A then
  read A): batching can re-order against later non-batched calls.
  Only batch tool surfaces whose bulk form is documented order-stable.
- **Mixed-cost bulk APIs** where batch cost is super-linear in N
  (some search backends): the batching gain reverses past a threshold.
  Set `max_batch_size` to the empirical sweet spot, not infinity.

## Files

- `window.py` — `BatchingWindow`, `Pending`, `BatchSizeMismatch`,
  `WindowClosed`. ~180 lines, stdlib only.
- `example.py` — four runnable scenarios with assertions.

## Worked example output

```
=== scenario 1: size-cap trips, then deadline picks up trailer ===
after-submits state:  flushes_total=2, pending_count=1, size_trips=2
after-tick state:     flushes_total=3, pending_count=0, deadline_trips=1
bulk_fn call_log sizes: [3, 3, 1]
first batch contents:  ['/data/0.txt', '/data/1.txt', '/data/2.txt']

=== scenario 2: deadline-only trip ===
tick at +20ms flushed: 0
tick at +30ms flushed: 2
bulk_fn call_log: [['/etc/hosts', '/etc/passwd']]

=== scenario 3: bulk_fn raises -> every handle inherits ===
manual flush drained: 3
errors: [('a', 'upstream 503 for batch of 3'),
         ('b', 'upstream 503 for batch of 3'),
         ('c', 'upstream 503 for batch of 3')]

=== scenario 4: close() drains, then rejects further submits ===
submit-after-close rejected: True

=== all assertions passed ===
```

7 single calls under `max_batch_size=3, max_wait_s=50ms` collapsed
into 3 bulk calls of size [3, 3, 1] — a 7→3 fanout reduction with the
trailing item flushed by the deadline rather than waiting for a 4th
that may never come.

Run it yourself:

```
python3 example.py
```

## Composition

- **`tool-call-retry-envelope`** — wrap the *bulk_fn*, not individual
  submits. The envelope sees one logical retryable unit per batch; the
  fanout-of-error pattern in scenario 3 is exactly the shape it
  expects.
- **`streaming-cancellation-token`** — register `window.flush(now)` as
  a cleanup so a cancel mid-window does not silently drop the pending
  items.
- **`rate-limit-token-bucket-shared`** — debit the bucket *per-batch*,
  not per-submit. The whole point of this template is that the bulk
  call is the rate-limit unit.
- **`agent-decision-log-format`** — log one row per *flush* (with
  trigger ∈ `{size_cap, deadline, manual}`, batch_size, wall-time
  saved estimate), not one per submit. The submit log is in the agent
  trace; the batching decision is what's interesting here.

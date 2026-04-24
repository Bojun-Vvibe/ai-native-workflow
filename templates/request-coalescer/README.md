# `request-coalescer`

Collapse N concurrent identical in-flight requests into 1 upstream
call. The first caller for a given key triggers the upstream; every
caller arriving while that call is still in flight attaches to the
same future and receives the same result (or the same exception).
The instant the upstream call completes, the in-flight slot is
released — the **very next** call after completion fires upstream
again.

This is *not* a result cache. The two patterns are complementary:

| | `request-coalescer` (this) | `tool-result-cache` |
|---|---|---|
| Lifetime | Strictly in-flight: ms-scale | Per-entry `ttl_s`: s-to-h scale |
| Mental model | "Do this work once *right now*" | "Remember this answer for later" |
| Memory cost | Bounded by max concurrent fan-in | Bounded by entry count × payload size |
| Stale-result risk | Zero (slot is gone the moment the call returns) | Non-zero (must reason about TTL vs upstream mutation) |
| Safety opt-in | **Mandatory** `safe_for_coalescing=True` | **Mandatory** `safe_tools` allowlist |

Use both together when both are warranted. The coalescer should sit
*in front of* the cache: a coalesced miss-and-fill costs one upstream
call no matter how many concurrent callers triggered the miss.

## The problem

You have a service with bursty fan-in. A webhook arrives, ten parallel
workers spawn, eight of them call `expand_user(user_id=42)` within
the same 30ms window before the result is cached, and your upstream
sees an 8x amplification of every webhook. You add a 30-second
result cache and the amplification disappears, but now you've also
amplified every *stale* result for 30 seconds — which is wrong if
the user just changed their tier.

The coalescer fixes the burst-amplification half of the problem
without taking on the staleness half. Concurrent calls are absorbed;
sequential calls always hit upstream.

## The bug class it prevents

Coalescing a non-idempotent operation silently swallows side effects.
If two parallel `POST /charge` calls coalesce, you charged the user
once when you intended to charge twice (or, worse, you charged them
twice because the framework retried both). This template **refuses to
coalesce** unless the caller passes `safe_for_coalescing=True` at
construction time. Calling `.call()` without that flag raises
`CoalescerError` immediately, before the upstream is ever touched.

This is the same shape of mandatory opt-in as `tool-result-cache`'s
`safe_tools` allowlist. Both templates assume the worst-case caller
and force them to declare otherwise. In production, every silent-
swallow incident this template has seen would have been blocked by
this guard.

## Approach

`RequestCoalescer(key_fn, safe_for_coalescing)` holds an in-memory
`{key: _Slot}` map under a single `threading.Lock`. The first caller
for a given key creates the slot, becomes the **leader**, runs the
upstream call, populates `slot.result` or `slot.error`, sets the
event, and removes the slot from the map. Every concurrent caller
arriving in between is a **follower** — they increment `slot.waiters`,
release the lock, and `slot.event.wait()` until the leader signals.

Critical structural properties:

1. **Slot is removed in `finally`, not after success.** A leader that
   raises still wakes followers and still releases the slot. This
   prevents one bad call from wedging future callers behind a dead
   future.
2. **Followers re-raise the leader's exception**, not a wrapped one.
   Type identity is preserved so `except RateLimitError:` in the
   follower works the same way it would have if the follower had run
   the upstream call directly.
3. **The lock is held only across the dict mutation**, not across
   the upstream call. A 50ms upstream does not block a different-key
   caller on a `lookup` for 50ms. This is the difference between an
   amplification reducer and an accidental serialization point.

## Contract

- `key_fn(*args, **kwargs) -> hashable` is required. The coalescer
  has no idea which arguments are part of identity and which are
  volatile metadata; the caller declares it.
- `safe_for_coalescing=True` is **mandatory**. The constructor accepts
  it as `False` only so that test fixtures can construct the object
  without immediately triggering; the first `.call()` raises.
- Followers see the leader's exception by **identity** (same
  exception object). Don't mutate exception state; treat it as
  immutable.
- The coalescer is **per-instance**, not process-global. Two
  coalescers with the same `key_fn` do not share their in-flight
  table. This is intentional — a global coalescer would couple
  unrelated subsystems' burst behavior.
- `state()` returns a snapshot for tests and `/healthz`:
  `{inflight_keys, leaders, followers, errors}`. `leaders` is the
  number of upstream calls the coalescer has actually issued;
  `followers` is the number of calls it has absorbed; the
  amplification ratio is `(leaders+followers)/leaders`.

## Asyncio shape

The reference implementation is sync-thread-safe. The asyncio
equivalent is a one-line change: replace `_Slot.event` with an
`asyncio.Future`, drop the lock (the loop is single-threaded), and
have followers `await slot.future`. The opt-in safety guard, the
finally-release semantic, and the exception re-raise rule are
identical.

## Composes with

- `tool-result-cache` — coalescer in front, cache behind. A coalesced
  miss-and-fill costs one upstream call regardless of fan-in width.
- `structured-error-taxonomy` — the leader's exception class drives
  whether followers should retry; the coalescer itself takes no view.
- `tool-call-circuit-breaker` — the breaker decision happens *outside*
  the coalescer; you do not want N followers all observed as one
  call by the breaker's failure-rate counter.
- `agent-decision-log-format` — log one line per `.call()` with
  `role=leader` or `role=follower` and the same `coalesce_key` so a
  query can reconstruct the fan-in at incident time.

## Sample run

```
$ python3 templates/request-coalescer/examples/run_example.py
Scenario 1: 8 concurrent expand_user(42) → 1 upstream call
----------------------------------------------------------------------
  upstream_calls['expand_user'] = 1
  distinct result objects        = 1
  sample result                  = {'user_id': 42, 'name': 'User-42', 'tier': 'gold'}
  coalescer.state()              = {'inflight_keys': [], 'leaders': 1, 'followers': 7, 'errors': 0}

Scenario 2: leader raises → all 5 followers see the same exception
----------------------------------------------------------------------
  upstream_calls['raises']       = 1
  distinct error reprs           = 1
  sample error                   = RuntimeError('upstream is down (user_id=99)')
  coalescer.state()              = {'inflight_keys': [], 'leaders': 1, 'followers': 4, 'errors': 1}

Scenario 3: 3 SEQUENTIAL calls → 3 upstream calls (not a cache)
----------------------------------------------------------------------
  upstream_calls['expand_user'] = 3
  coalescer.state()              = {'inflight_keys': [], 'leaders': 3, 'followers': 0, 'errors': 0}

Scenario 4: missing safe_for_coalescing=True → CoalescerError
----------------------------------------------------------------------
  raised: CoalescerError('RequestCoalescer requires explicit safe_for_coalescing=True; coalescing operations with side effects silently swallows them.')
```

Four things to read out of the trace above:

1. **Scenario 1 is the headline result.** Eight threads, one upstream
   call, identical results returned to all eight callers. The
   `distinct result objects = 1` line is checked via `id()` — it's
   the *same Python object*, not just equal copies. That's the
   property that makes the coalescer correct under reference equality
   (e.g. when callers compare `result is sentinel`).
2. **Scenario 2 shows the same shape works for failures.** The
   leader's `RuntimeError` is propagated to all five callers
   verbatim. The `errors=1` counter records *one* upstream failure,
   not five — the failure-rate metric in the breaker upstream of
   this coalescer should match the same denominator.
3. **Scenario 3 confirms this is not a cache.** Three sequential
   calls, three upstream calls. If you wanted them to share, you
   wanted `tool-result-cache`.
4. **Scenario 4 is the safety guard.** A caller who forgot to
   declare `safe_for_coalescing=True` gets a loud `CoalescerError`
   on their very first call, before any upstream is touched. This
   is what makes "we accidentally coalesced two `POST /charge`
   calls" a category of bug this template cannot produce.

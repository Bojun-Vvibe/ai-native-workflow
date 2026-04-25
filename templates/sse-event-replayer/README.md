# sse-event-replayer

Server-side replayer for **resumable Server-Sent-Events-style streams**.
The producer-side companion of [`sse-reconnect-cursor`](../sse-reconnect-cursor/):
the cursor template owns the consumer's correctness on reconnect (don't
re-deliver, don't silently rewind, don't tight-loop on a dead upstream);
this template owns the producer's correctness when a reconnecting client
hands back a `Last-Event-ID` and asks "what did I miss?".

The class itself is in-memory and stdlib-only — no I/O on the hot path,
no clocks, no transport. Durability is layered *underneath* the
replayer (a JSONL append-only file the producer writes to *before*
calling `append`, and that gets fed back into a fresh `EventReplayer`
on process restart). Keeping persistence out of this class is what
lets the worked example drive every verdict deterministically without
touching a filesystem or a fake clock.

## The problem

A naïve "remember the last N events in a deque, hand back everything
after the cursor on reconnect" implementation is wrong in four
distinct ways:

| Bug class | Naïve behaviour | What this replayer does |
|---|---|---|
| Cursor predates retention | Silently returns the tail, consumer skips events without knowing | `TOO_OLD` verdict + `oldest_retained_id` so caller can fall back to a snapshot |
| Cursor ahead of latest (replica desync) | Returns empty, consumer waits forever | `FUTURE_CURSOR` verdict + `latest_id` so caller can detect the desync |
| Producer re-appends same id with different payload | Silently overwrites or silently keeps either copy | `IdPayloadConflict` raised — refuses to paper over a producer bug |
| Producer appends an id older than the last id | Silently grows out-of-order, breaks `since()` invariants | `NonMonotonicId` raised |

Same-id-**same**-payload re-append *is* silently absorbed — a flaky
writer retrying after a network blip is a normal operational event,
not a bug. The boundary between "idempotent retry" and "bug" is
"does the payload byte-equal what we already have?".

## Verdicts

`since(last_event_id)` returns one of:

* **`DELIVER`** — events to ship in `result.events`.
* **`EMPTY`** — cursor is current; nothing to ship (also returned for
  a `None` cursor against an empty log, so the consumer can simply
  wait for new traffic).
* **`TOO_OLD`** — cursor is more than one event behind the oldest id
  we still hold; `result.oldest_retained_id` tells the caller where
  the surviving tail starts so they can decide between "snapshot +
  resume" and "restart from scratch".
* **`FUTURE_CURSOR`** — cursor is strictly ahead of our `latest_id`.
  The consumer is talking to a stale replica or its persisted cursor
  is corrupt. `result.latest_id` lets the caller decide whether to
  pin to a fresher backend or surface a hard error.

The boundary case `last_event_id == oldest_retained_id - 1` is
intentionally **DELIVER** (we still have everything strictly after
that cursor); only `< oldest - 1` is `TOO_OLD`. The worked example
verifies both sides of the boundary.

## When to use it

* You record an LLM token stream / tool-output stream / log tail to
  durable storage and need to let dropped consumers resume without
  re-running the upstream computation.
* You run multiple consumer replicas (UI tabs, parallel sub-agents)
  off one event log and each wants its own `Last-Event-ID` cursor.
* You want a single class to compare against in tests rather than
  re-implementing reconnect logic per transport.

## When NOT to use it

* The upstream producer is itself idempotent and cheap to re-run from
  scratch on every reconnect. A replayer adds memory and a contract
  surface for zero benefit.
* The protocol uses opaque UUID event ids. The replayer requires
  monotonic `int` ids — same constraint as `sse-reconnect-cursor`,
  for the same reason: you cannot answer "did the consumer rewind?"
  on UUIDs.
* You need a durable, crash-safe queue. Use a real broker
  (Kafka / Redis Streams / NATS JetStream). This template is a
  correctness-shape, not a database.

## Knobs

| knob | default | notes |
|---|---|---|
| `max_retained` | 1024 | Count-based retention. Time-based retention is a trivial extension (inject a clock; evict where `now - event_wallclock > ttl`); we kept the worked example clock-free on purpose. |

## Sample run

```
$ python3 worked_example.py
=== sse-event-replayer worked example ===

[1] cold consumer (last_event_id=None) -> DELIVER all
  since(None)                  verdict=DELIVER        events=[1, 2, 3, 4, 5] oldest_retained_id=None latest_id=None

[2] reconnect with last_event_id=3 -> DELIVER tail [4,5]
  since(3)                     verdict=DELIVER        events=[4, 5] oldest_retained_id=None latest_id=None
    (cursor caught up; another since(5) -> EMPTY)
  since(5)                     verdict=EMPTY          events=[] oldest_retained_id=None latest_id=None

[3] retention rolls past consumer's cursor -> TOO_OLD
    snapshot: retained=4 oldest_id=7 latest_id=10 evicted=6
  since(2)                     verdict=TOO_OLD        events=[] oldest_retained_id=7 latest_id=None
  since(6) [boundary]          verdict=DELIVER        events=[7, 8, 9, 10] oldest_retained_id=None latest_id=None

[4] consumer cursor ahead of our latest -> FUTURE_CURSOR
  since(99)                    verdict=FUTURE_CURSOR  events=[] oldest_retained_id=None latest_id=5

[5] same-id-same-payload re-append is silently absorbed
    appended=1 duplicate_absorbed=1 retained=1

[6] same-id-different-payload -> IdPayloadConflict
    raised: id=1 re-appended with different payload

[7] non-monotonic append -> NonMonotonicId
    raised: id=4 <= last_id=5; producer is not monotonic

[final stats] r.snapshot() =
{
  "latest_id": 5,
  "max_retained": 8,
  "oldest_id": 1,
  "retained": 5,
  "stats": {
    "appended": 5,
    "deliver_calls": 2,
    "duplicate_absorbed": 0,
    "empty_calls": 1,
    "evicted": 0,
    "future_cursor_calls": 1,
    "too_old_calls": 0
  }
}
```

## Composes with

* [`sse-reconnect-cursor`](../sse-reconnect-cursor/) — the consumer-side
  cursor protocol that hands the `last_event_id` to `since()`.
* [`tool-call-replay-log`](../tool-call-replay-log/) — durable
  fingerprinted append-only log; an `EventReplayer` is the read-side
  of one of those logs scoped to an SSE-shaped stream.
* [`streaming-chunk-reassembler`](../streaming-chunk-reassembler/) —
  the per-chunk dedup / gap-detection layer one level *up* from the
  replayer (the replayer guarantees ordered delivery; the reassembler
  copes with chunks delivered out of order *within* one connection).

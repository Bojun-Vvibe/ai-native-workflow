# sse-reconnect-cursor

Pure cursor-tracker for **resumable Server-Sent-Events-style streams** —
LLM token streams, tool-output streams, log tails, anywhere the upstream
can drop and the protocol gives you a `Last-Event-ID` to resume from.

The transport layer (urllib / aiohttp / your SDK) is the caller's job.
This template owns the *correctness* part of resume that ad-hoc transport
code consistently gets wrong:

| Bug class | What ad-hoc code does | What this cursor does |
|---|---|---|
| Silent re-delivery after reconnect | Re-yields the replay window to the consumer | `SKIP_DUPLICATE` verdict, `last_event_id` does **not** move |
| Silent rewind (server replica desync) | Quietly accepts an id we never saw and "re-delivers" it | `REJECT_REWIND` verdict — caller decides to abort |
| Reconnect storm against permanently-broken upstream | Tight loop on `recv()` failure | Per-window attempt budget, `GIVE_UP` after exhaustion |
| Ignoring `Retry-After` server hint | Local backoff only | Server hint is a *floor*, never overridden downward |
| String / UUID event ids | `if id == last_id` substring guesses | Type-checked monotonic `int` only — UUIDs cannot be safely compared for "did we rewind?" |

## Problem

Streaming LLM and tool protocols inevitably drop. The naive resume path
("reconnect, send `Last-Event-ID`, keep yielding") has three failure modes
that bite in production:

1. **Re-delivery.** The server replays the tail of what it sent us, but
   we've already handed those tokens to the consumer. Without a cursor
   the consumer sees `"The quick brown brown fox"`.
2. **Rewind.** The server is actually a load-balanced pool; a backend
   replica is behind. It hands us an id strictly *less* than our cursor.
   Without a check the consumer silently re-processes stale work.
3. **Reconnect spin.** Upstream is dead. The transport reconnects in a
   tight loop. The mission burns its quota and the agent loop wedges
   waiting on a stream that will never produce.

This template is pure logic with an injected clock — the transport never
mixes with the correctness rules.

## When to use

- You consume a streamed protocol where ids are (or can be made) monotonic
  integers.
- The stream is long-lived enough that reconnects happen in normal
  operation, not just during incidents.
- You need the resume decision to be **testable** — i.e. unit-tested
  without standing up a server.

## When NOT to use

- The protocol guarantees exactly-once delivery end-to-end (e.g. a
  message broker with consumer offsets). Then the broker's offset *is*
  the cursor.
- Event ids are unordered UUIDs and cannot be made monotonic. Use a
  different idempotency strategy (content hash dedup window —
  `tool-call-deduplication`).
- The stream is so short (one prompt → ≤ a few seconds) that any drop
  is fatal anyway. Just abort.

## Knobs

| Param | Meaning | Sensible default |
|---|---|---|
| `max_attempts_per_window` | Reconnects allowed inside `window_s` | `3` |
| `window_s` | Sliding window for the budget | `10.0` |
| `min_backoff_s` | Floor between reconnects (server hint can raise) | `0.1` |
| `now` | Monotonic clock callable; inject for tests | `time.monotonic` |
| `_seen_tail_cap` | How many delivered ids to retain for rewind detection | `1024` |

## Outputs

`consider(event_id)` returns an `EventDecision` with one of three verdicts:

- `DELIVER` — new event, advance cursor, hand to consumer.
- `SKIP_DUPLICATE` — already-delivered, just discard.
- `REJECT_REWIND` — server protocol violation; **caller must abort or
  alert**. The cursor does not move.

`consider_reconnect(server_retry_after_s=None)` returns a
`ReconnectDecision`:

- `GO` — allowed; the slot is claimed.
- `WAIT` — `wait_s` tells you how long.
- `GIVE_UP` — budget exhausted; do not reconnect, surface as failure.

## Worked example

```bash
python3 worked_example.py
```

Five scenarios in one run:

1. Clean delivery of events 0..3.
2. Drop, reconnect (`GO`, used=1/3), server replays 2,3 → both `SKIP`,
   then 4 is `DELIVER`.
3. Drop again, server says `Retry-After: 0.5s` (larger than our 0.1s
   floor) → `WAIT wait_s=0.5`.
4. Burn the rest of the budget, see `GIVE_UP`. Advance the clock past
   `window_s`; budget refills, `GO` again.
5. Manufactured rewind: an id in `(oldest_seen, last_event_id]` that is
   not in our delivered tail surfaces as `REJECT_REWIND` with a
   diagnostic `reason=` string — proving the check is real, not
   trusting-the-tail.

Final `last_event_id == 4`; nothing in `delivered` is repeated.

## Composes with

- **`tool-call-retry-envelope`** — the cursor's `GIVE_UP` is exactly the
  signal that says "do not retry the underlying request, classify as
  `do_not_retry`".
- **`structured-error-taxonomy`** — `REJECT_REWIND` classifies as
  `attribution=upstream, retryability=do_not_retry` (the upstream is
  contradicting itself; another attempt will not fix it).
- **`exponential-backoff-with-jitter`** — when the cursor returns
  `WAIT`, the caller can pass `wait_s` straight to its sleep loop, or
  feed it as a floor into the jitter planner if it wants randomness on
  top.
- **`agent-decision-log-format`** — every `REJECT_REWIND` and
  `GIVE_UP` should be one decision-log line with `exit_state=error`
  so post-mortems are queryable.

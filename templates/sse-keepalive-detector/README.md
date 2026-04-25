# sse-keepalive-detector

Pure liveness detector for **streaming protocols that mix real events with
keepalives** — LLM token streams, SSE channels, gRPC server-streaming RPCs,
log tails — anywhere "the stream went quiet" is ambiguous between *the
producer is alive but has nothing to say right now* and *the connection is
dead*.

The transport layer (urllib / aiohttp / your SDK) is the caller's job. This
template owns the *liveness verdict* part most ad-hoc stream watchdogs get
wrong:

| Bug class | What ad-hoc code does | What this detector does |
|---|---|---|
| Single-threshold timeout fires on healthy idle stream | Reconnects every time the model pauses for a tool call | `IDLE_BUT_ALIVE` verdict — caller does NOT reconnect |
| Single-threshold timeout misses dead-but-recently-alive | Watches "time since last *anything*", treats keepalive as token | Two thresholds: real-event idle, keepalive idle |
| Watchdog only re-checks on event arrival | Wedged stream that emits zero events forever is never noticed | `verdict(now=…)` and `verdict()` (clock-driven) flip without a new `observe()` |
| Inverted-threshold misconfig | Caller passes a 30s keepalive idle and a 5s real-event idle and the detector never alerts | `DetectorConfigError` raised at construction (`keepalive_idle_s <= real_event_idle_s` or fail loudly) |
| Cold-start blind spot | Detector returns "no events yet, all good" forever if the stream never connects | `DEAD` verdict once `(now - constructed_at) > keepalive_idle_s` with zero events |

## Problem

Real LLM streams send tokens in bursts then pause for tool execution; a 30s
gap between *real* chunks is normal mid-mission. Keepalives are supposed to
be cheap heartbeats — a 30s gap between *those* means the server isn't even
alive. Conflating the two thresholds either alarms on healthy idle streams
or misses dead-but-recently-alive ones.

This detector separates the two questions:

- **Is the stream producing useful output?** — `real_event_idle_s` window.
- **Is the connection still up at all?** — `keepalive_idle_s` window.

…and combines them into a four-state verdict the caller's policy can branch
on without re-reasoning:

```
HEALTHY          — saw a real event within real_event_idle_s
IDLE_BUT_ALIVE   — no real event in window, but a keepalive within keepalive_idle_s
STALLED          — neither in window — cancel + reconnect
DEAD             — never observed anything past keepalive_idle_s — never connected
```

## When to use

- You consume a streamed protocol that distinguishes real events from
  keepalive frames (SSE comment lines `:keepalive\n\n`, `event: ping`,
  WebSocket pong frames, gRPC keepalive pings).
- The protocol's normal pause between real events is long enough that a
  single timeout would either alarm constantly or miss real failures.
- A watchdog process needs to decide "should I cancel this stream?"
  *without* requiring a new event to arrive (the stream might be wedged
  in `recv()` producing zero events).

## When NOT to use

- The protocol has no keepalive concept (raw byte streams, plain TCP
  sockets without an application-layer heartbeat). Use a single-threshold
  watchdog instead — there's no second signal to disambiguate.
- You need throughput / TTFT measurement. Use `streaming-token-rate-meter`
  — that's a different question (rate, not liveness).
- You need cursor / resume correctness on reconnect. Use
  `sse-reconnect-cursor` — orthogonal concern.

## How it composes

- **`streaming-cancellation-token`**: when this detector returns `STALLED`,
  call `cancel("stream_stalled")` on the cancellation token. This template
  *decides* to cancel; that one *delivers* the cancel.
- **`sse-reconnect-cursor`**: after a `STALLED` cancel, hand the cursor's
  `last_event_id` to the reconnect path. This detector says *when* to
  reconnect; that one says *where* to resume from.
- **`tool-call-timeout-laddered`**: this detector's `STALLED` verdict is
  the signal to escalate from soft to hard timeout — the soft tier asks
  the producer to checkpoint, the hard tier tears down based on this
  verdict.
- **`agent-decision-log-format`**: log one line per `STALLED` / `DEAD`
  flip, with the snapshot fields as the structured payload.

## Public API

```python
from detector import Detector

det = Detector(
    real_event_idle_s=30.0,    # max gap between real events before "no useful output"
    keepalive_idle_s=10.0,     # max gap between any frame before "connection dead"
    # now_fn=time.monotonic   # injected; tests pass a fake clock
)

# On every received frame:
det.observe(now_seconds, kind="real")        # token chunk, message event, etc.
det.observe(now_seconds, kind="keepalive")   # ":keepalive", "event: ping"

# At any moment (event-driven OR clock-driven):
verdict = det.verdict()                # HEALTHY | IDLE_BUT_ALIVE | STALLED | DEAD
snap    = det.snapshot()               # full structured snapshot for logs
```

Construction-time `DetectorConfigError` if `real_event_idle_s <= 0`,
`keepalive_idle_s <= 0`, or `keepalive_idle_s > real_event_idle_s` (a
keepalive idle threshold *bigger* than the real-event one is almost
certainly a config bug — keepalives are supposed to be the cheaper, more
frequent signal).

A `kind="real"` observation also bumps the keepalive watermark — a chatty
stream that never sends explicit keepalives must not flap to `STALLED` the
moment real events pause. A `kind="keepalive"` observation does NOT bump
the real-event watermark (that would defeat the entire point).

## Worked example

`worked_example.py` runs five scenarios against a deterministic injected
clock so the output is byte-stable.

### Verified output

```
================================================================
Scenario 1: HEALTHY — real tokens every 0.5s for 5s
================================================================
  real_event_count=10
  keepalive_count=0
  seconds_since_last_real=0.00
  verdict=HEALTHY

================================================================
Scenario 2: IDLE_BUT_ALIVE — no real tokens for 40s, keepalives every 5s
================================================================
  real_event_count=1
  keepalive_count=8
  seconds_since_last_real=40.00
  seconds_since_last_keepalive=0.00
  verdict=IDLE_BUT_ALIVE  (do NOT reconnect — server is alive)

================================================================
Scenario 3: STALLED — real and keepalives both stop
================================================================
  seconds_since_last_real=18.00
  seconds_since_last_keepalive=16.00
  verdict=STALLED  (cancel + reconnect)

================================================================
Scenario 4: DEAD — never observed anything, past keepalive window
================================================================
  at t+4s (warm-up): verdict=IDLE_BUT_ALIVE
  at t+6s (past keepalive_idle): verdict=DEAD

================================================================
Scenario 5: Watchdog flips verdict WITHOUT a new observe()
================================================================
  immediately after observe: verdict=HEALTHY
  +4s, no new observe: verdict=HEALTHY
  +9s total, no new observe: verdict=STALLED

All scenarios passed.
```

### What each scenario proves

- **Scenario 1** — the obvious good case. Real tokens at 2 Hz easily satisfy
  a 10s real-event window. `keepalive_count=0` because we never sent any —
  the detector correctly treats real events as also satisfying the
  keepalive watermark.
- **Scenario 2** — the failure mode this template exists for. 40s with no
  real events but keepalives every 5s correctly stays `IDLE_BUT_ALIVE`. A
  single-threshold watchdog set to 30s would have triggered a useless
  reconnect.
- **Scenario 3** — both signals dead. After 16s of total silence (past the
  5s keepalive window and the 10s real-event window) verdict is `STALLED`.
  This is the actionable signal — caller cancels and reconnects.
- **Scenario 4** — cold-start. Within the keepalive warm-up window
  (`t+4s < 5s`) verdict is `IDLE_BUT_ALIVE` (could still arrive). Past it
  (`t+6s > 5s`) with zero events ever observed verdict is `DEAD`. The
  ad-hoc bug here is "I'll wait for the first event to start the timer" —
  which means a never-connected stream is never alarmed.
- **Scenario 5** — the watchdog property. After one `observe()` and 9s of
  zero further calls, `verdict()` (called by a periodic watchdog with no
  new event input) flips to `STALLED`. This is the property that lets a
  watchdog process detect a stream wedged inside `recv()` — the stream
  itself produces no events, so an event-driven detector would never know.

## Run it

```bash
python3 worked_example.py
```

## Adapt this section

When you copy this template into your own repo, the only project-specific
choices are the two thresholds:

- `real_event_idle_s` — the upper bound on "how long a healthy stream can
  go without producing a useful token / chunk." For a chatbot streaming
  raw tokens, 5–10s is plenty. For an agent that pauses for long tool
  calls, 60–120s is more honest.
- `keepalive_idle_s` — match it to the server's advertised keepalive
  interval × 2–3. A server sending a `:keepalive` every 5s warrants
  `keepalive_idle_s=15.0`. Setting it shorter alarms on packet jitter;
  setting it much longer wastes the entire premise of a keepalive.

If your protocol does NOT distinguish real events from keepalives, do not
use this template — pick a single-threshold watchdog. The whole point here
is the two-signal disambiguation.

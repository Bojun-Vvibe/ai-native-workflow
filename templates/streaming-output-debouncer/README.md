# streaming-output-debouncer

Coalesce a token stream into fewer, larger flush events. Releases a batch when
either the time window expires (default 50ms) or the buffer hits a size cap
(default 256 chars), whichever comes first. Single-threaded, stdlib only,
caller-supplied clock.

## When to use

- You're piping LLM token output into a websocket, terminal repaint, or
  log line and seeing flush amplification (1 frame per token).
- Downstream rendering or transport overhead per flush is non-trivial
  (TLS frames, React reconciles, structured-log emit).
- You want a deterministic, testable flush boundary that doesn't depend
  on threads, timers, or asyncio.

## Why this exists

- Naive 1-flush-per-token streams collapse on bursty arrivals — the
  network produces 30 chunks in 5ms and you fire 30 separate frames.
- Pure size-based batching adds latency at the tail of slow streams;
  pure time-based batching can buffer too much during a burst.
- Combining both bounds latency *and* batch size, with an explicit
  `flush_final()` to drain the tail.

## How to run the example

```
python3 example.py
```

Simulates a 60-token stream with 4 bursts of varying tightness, using a
fake clock so the run is deterministic. Compares naive 1-per-token flush
count against debounced flush count, then prints each flush event with
its trigger reason (`interval` | `buffer` | `final`).

## Example output

```
============================================================
streaming-output-debouncer — worked example
Total tokens: 60
============================================================

Raw flush count (1-per-token): 60
Debounced flush count:         6
Reduction:                     54 fewer flushes (90%)

Flush events:
  #01 t= 105.0ms  reason=buffer    chunks=11  bytes= 66  'tok00 tok01 tok02 tok03 tok04 tok05 tok0…'
  #02 t= 270.0ms  reason=interval  chunks=10  bytes= 60  'tok11 tok12 tok13 tok14 tok15 tok16 tok1…'
  #03 t= 320.0ms  reason=interval  chunks=10  bytes= 60  'tok21 tok22 tok23 tok24 tok25 tok26 tok2…'
  #04 t= 370.0ms  reason=interval  chunks=10  bytes= 60  'tok31 tok32 tok33 tok34 tok35 tok36 tok3…'
  #05 t= 635.0ms  reason=interval  chunks=10  bytes= 60  'tok41 tok42 tok43 tok44 tok45 tok46 tok4…'
  #06 t= 680.0ms  reason=final     chunks= 9  bytes= 54  'tok51 tok52 tok53 tok54 tok55 tok56 tok5…'

============================================================
Flushes by reason: {'buffer': 1, 'interval': 4, 'final': 1}
============================================================
```

## Lessons from real use

Always call `flush_final()` — without it the tail of every stream is silently
dropped on the floor. The 50ms / 256B defaults are tuned for terminal repaints;
for websocket fan-out to browsers, raise `min_interval_s` to ~120ms (matches
typical animation frames) and watch buffer-triggered flushes dominate during
bursts. If you find yourself wanting threads or timers, you almost certainly
want a different primitive — this one is intentionally pull-driven.

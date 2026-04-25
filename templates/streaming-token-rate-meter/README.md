# streaming-token-rate-meter

Pure rate / latency observer for **streamed LLM token output** (or any
chunked stream). Lets a watchdog detect a stalling upstream and lets a
report show what the user *actually felt* — TTFT, current tokens/sec,
inter-chunk gap — rather than a single dishonest cumulative average.

## Problem

Two distinct streaming-failure modes look identical to a naive observer:

| Mode | What the user sees | What an "average tok/s" log shows |
|---|---|---|
| Cold-start, then bursty | "It hung for 1.5s then exploded" | Same as steady ~30 tok/s. Indistinguishable. |
| Healthy then wedged | "Half the response, then nothing" | Same as steady-but-slow. Indistinguishable. |

A single cumulative number hides both. This template gives the caller the
two numbers that distinguish them: **window tokens/sec** (what's
happening now) and **TTFT** (cold-start latency), plus a structural
**stall verdict** that flips even when *no new chunk arrives* — so a
watchdog can cancel a stream that is wedged in `recv()` and producing no
events at all.

## Why a sliding window, not an EWMA

Agents care about *"did the upstream just slow to a crawl in the last
second?"* much more than the long-run mean. EWMAs are over-smoothed for
this question. The window is a deque of `(t, n)` samples; old samples
age out lazily on the next call. Memory is bounded by `tokens_per_s
* window_s`.

## When to use

- You stream LLM output and want to set a per-call watchdog timeout that
  fires on **content-stall** (no tokens for N seconds), not just on
  total wall-clock.
- You want a real TTFT number per call so you can flag cold-start
  regressions per model / region.
- You want session reports to honestly distinguish "warm steady stream"
  from "long pause then burst".

## When NOT to use

- The protocol is non-streaming (request/response). Just measure
  end-to-end latency.
- You only care about completed-call cost; tokens-out is logged once.
- You already have an OTel histogram doing the same job. Use that.

## Knobs

| Param | Meaning | Default |
|---|---|---|
| `window_s` | Sliding window for "tokens/sec right now" | `1.0` |
| `stall_threshold_s` | Inter-chunk gap that flips `is_stalled=True` | `2.0` |
| `now` | Monotonic clock; inject for tests | `time.monotonic` |

## API

```python
m = StreamingTokenRateMeter(window_s=1.0, stall_threshold_s=2.0)
m.start()                                   # mark request-send time
for chunk in stream:
    m.observe(now_s=time.monotonic(),
              tokens_delta=chunk.token_count)
    snap = m.snapshot()
    if snap.is_stalled:
        cancel_request()
        break
report(snap)
```

`snapshot()` returns a `RateSnapshot`:

| Field | Meaning |
|---|---|
| `elapsed_s` | Wall clock since `start()` |
| `total_tokens` | Sum of all `tokens_delta` so far |
| `chunks_seen` | Includes zero-token heartbeat chunks |
| `ttft_s` | First non-zero chunk; `None` until then |
| `window_tokens_per_s` | Recent rate (over `window_s`) |
| `last_gap_s` | Gap between the last two chunks |
| `max_gap_s` | Largest inter-chunk gap so far |
| `is_stalled` | `True` if *current* gap (now - last_chunk) > `stall_threshold_s` |
| `cumulative_tokens_per_s` | `total / elapsed` — for whole-run reports |

Heartbeat / keepalive chunks (`tokens_delta=0`) update gap state and
chunk counts but never set TTFT or contribute to throughput. That's the
correct accounting: a server sending keepalives is *not* producing
tokens, but it *is* still "alive enough that we shouldn't cancel".

## Worked example

```bash
python3 worked_example.py
```

Three scenarios, all asserted:

1. **Healthy** — TTFT=0.10s, 50 tok/s steady for 2s. Final snapshot:
   `window_tokens_per_s=50.0`, `cumulative_tokens_per_s≈47.6`,
   `is_stalled=false`.
2. **Cold-start then burst** — TTFT=1.5s, then 80 tokens in the next
   1.0s. End snapshot: `window_tokens_per_s=81.0` but
   `cumulative_tokens_per_s≈32.4`. A caller logging only the cumulative
   number would miss the burst entirely.
3. **Stall detected without a new chunk** — 5 chunks then silence.
   1.5s after the last chunk: `is_stalled=false`,
   `window_tokens_per_s=0.0` (window aged out). 2.5s after the last
   chunk: `is_stalled=true` *with no new `observe()` call required*.
   A watchdog calling `snapshot()` periodically can cancel the upstream
   from the snapshot alone.

## Composes with

- **`tool-call-timeout-laddered`** — `is_stalled=True` is the signal
  to escalate from soft-timeout to hard-timeout instead of waiting out
  the rest of the wall-clock budget.
- **`streaming-cancellation-token`** — the watchdog reads
  `snapshot()`, the cancellation token actually tears down the stream.
- **`metric-baseline-rolling-window`** — emit `ttft_s` and
  `cumulative_tokens_per_s` per call; the baseline detector tells you
  when today's TTFT is anomalous against the last 14 days.
- **`agent-decision-log-format`** — log one line per cancelled stream
  with `exit_state=error` plus the snapshot, so post-mortems can sort
  stalls from cold-starts from genuinely-slow models.

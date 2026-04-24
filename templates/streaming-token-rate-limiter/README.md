# `streaming-token-rate-limiter`

Per-session output-token rate limiter for streaming model responses,
with **cooperative yield** semantics. The limiter never sleeps; it
tells the caller exactly how long to yield. That makes it usable from
sync, threaded, OR asyncio code, and trivially deterministic in tests.

## What it solves

A model is happily streaming 50 tokens/sec into your session, but:

- Your downstream consumer (UI, TTS, captioner, log shipper) can only
  swallow ~10 tok/s sustained without backpressure damage.
- You set a per-session output budget of 60 tokens and want the stream
  to **stop cleanly at the cap**, not after the fact.
- You want a small burst budget (e.g. 20 tokens) so short responses
  feel snappy, but anything longer is throttled to the sustainable
  rate.

A single primitive handles all three: a token-bucket (capacity +
refill rate) plus a hard `max_total_tokens` cap.

## When to use

- You are the producer or proxy of a streamed model response and you
  control when the next chunk is forwarded.
- You want backpressure that is **cooperative** (the caller chooses
  how to yield) rather than blocking.
- You want determinism — caller injects `now_s`, so unit tests don't
  need real time.

## When NOT to use

- You don't control the producer and can't drop/delay chunks. The
  limiter cannot un-emit tokens that already left the model.
- You need **fleet-wide** rate limiting across processes or hosts —
  this is single-session, in-memory. Use
  `rate-limit-token-bucket-shared` for that.
- You need to throttle *input* prompt tokens — that's a budget
  problem, not a rate problem; see `token-budget-tracker`.

## Anti-patterns this prevents

- **"Stop at cap" implemented as "stop after cap"**: emitting the
  chunk that pushes you over `max_total_tokens` and then refusing
  the next one. The limiter refuses the chunk that *would* cross
  the cap, so the session ends cleanly on a chunk boundary.
- **Sleeping inside the limiter**: makes it impossible to use from
  asyncio, impossible to test deterministically, and surprising when
  it holds a lock during the sleep.
- **Coupling burst and sustained rate**: people often use a single
  "rate" knob and either get no burst at all or unbounded burst.
  Separate `capacity` (burst) and `tokens_per_sec` (sustained) is
  the standard token-bucket separation.

## API surface

`StreamingTokenLimiter(capacity, tokens_per_sec, max_total_tokens)`

| Method | Returns | Notes |
|---|---|---|
| `admit(n_tokens, now_s)` | `(verdict, wait_s)` | `verdict ∈ {"emit","wait","stop"}`. State only mutates on `"emit"`. |
| `state()` | `dict` | `{tokens_available, emitted_total, remaining_session_budget, capped}` — safe to log every chunk. |

Verdicts:

- `("emit", 0.0)`  — caller MAY emit the chunk now; tokens debited.
- `("wait", s)`    — caller MUST yield `s` seconds, then call `admit` again.
- `("stop", 0.0)`  — session cap reached; caller MUST end the stream.

## Files

- `limiter.py` — pure-stdlib reference (also exposes `python limiter.py demo`).
- `example.py` — end-to-end worked example (verbatim output below).

## Smoke test — `python3 example.py`

A producer wants to push 5-token chunks back-to-back. Limiter is
sized: `capacity=20`, `tokens_per_sec=10`, `max_total_tokens=60`.

```
=== chunk-by-chunk trace ===
{"capped": false, "chunk": 0, "emitted_total": 5, "remaining_session_budget": 55, "t": 0.0, "tokens_available": 15.0, "verdict": "emit"}
{"capped": false, "chunk": 1, "emitted_total": 10, "remaining_session_budget": 50, "t": 0.0, "tokens_available": 10.0, "verdict": "emit"}
{"capped": false, "chunk": 2, "emitted_total": 15, "remaining_session_budget": 45, "t": 0.0, "tokens_available": 5.0, "verdict": "emit"}
{"capped": false, "chunk": 3, "emitted_total": 20, "remaining_session_budget": 40, "t": 0.0, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 4, "t": 0.0, "verdict": "wait", "wait_s": 0.5}
{"capped": false, "chunk": 4, "emitted_total": 25, "remaining_session_budget": 35, "t": 0.5, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 5, "t": 0.5, "verdict": "wait", "wait_s": 0.5}
{"capped": false, "chunk": 5, "emitted_total": 30, "remaining_session_budget": 30, "t": 1.0, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 6, "t": 1.0, "verdict": "wait", "wait_s": 0.5}
{"capped": false, "chunk": 6, "emitted_total": 35, "remaining_session_budget": 25, "t": 1.5, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 7, "t": 1.5, "verdict": "wait", "wait_s": 0.5}
{"capped": false, "chunk": 7, "emitted_total": 40, "remaining_session_budget": 20, "t": 2.0, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 8, "t": 2.0, "verdict": "wait", "wait_s": 0.5}
{"capped": false, "chunk": 8, "emitted_total": 45, "remaining_session_budget": 15, "t": 2.5, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 9, "t": 2.5, "verdict": "wait", "wait_s": 0.5}
{"capped": false, "chunk": 9, "emitted_total": 50, "remaining_session_budget": 10, "t": 3.0, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 10, "t": 3.0, "verdict": "wait", "wait_s": 0.5}
{"capped": false, "chunk": 10, "emitted_total": 55, "remaining_session_budget": 5, "t": 3.5, "tokens_available": 0.0, "verdict": "emit"}
{"chunk": 11, "t": 3.5, "verdict": "wait", "wait_s": 0.5}
{"capped": true, "chunk": 11, "emitted_total": 60, "remaining_session_budget": 0, "t": 4.0, "tokens_available": 0.0, "verdict": "emit"}
{"capped": true, "chunk": 12, "emitted_total": 60, "remaining_session_budget": 0, "t": 4.0, "tokens_available": 0.0, "verdict": "stop"}

=== summary ===
{
  "chunks_emitted": 12,
  "effective_rate_tok_per_s": 15.0,
  "final_state": {
    "capped": true,
    "emitted_total": 60,
    "remaining_session_budget": 0,
    "tokens_available": 0.0
  },
  "tokens_emitted": 60,
  "total_yield_s": 4.0,
  "wall_time_s": 4.0
}
```

Things to notice:

- Chunks 0..3 emit immediately — that's the 20-token burst budget.
- From chunk 4 on, the producer is throttled to a steady 0.5s yield
  per 5-token chunk = 10 tok/s, exactly the sustained refill rate.
- The session ends cleanly on chunk 12 with verdict `"stop"` — the
  limiter refused the chunk that would cross the 60-token cap.
- Effective rate is 15 tok/s overall: the burst (20 tok in 0s) plus
  sustained 10 tok/s averages out higher than the steady-state rate.

## Composition

- `token-budget-tracker` — that template tracks $ and tokens *across*
  sessions; this one shapes the rate *within* a session. Use both.
- `model-output-truncation-detector` — when this limiter returns
  `"stop"`, downstream code sees a truncated response; the truncation
  detector classifies it correctly (`reason="rate_limit_cap"`).
- `partial-output-checkpointer` — if a session is cut at the cap, the
  checkpointer can persist the partial response so a later session can
  resume from where the cap fired.

## Non-goals

- Not a multi-process limiter (use `rate-limit-token-bucket-shared`).
- Not a fairness scheduler across sessions (each session has its own
  limiter; the caller decides scheduling between them).
- Not a budget tracker across requests/days (different concern).

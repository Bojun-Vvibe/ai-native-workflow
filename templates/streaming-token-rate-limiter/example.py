#!/usr/bin/env python3
"""End-to-end worked example for streaming-token-rate-limiter.

Simulates a model streaming 5-token chunks at 50 tok/s into a limiter
sized for 10 tok/s sustained, 20 tok burst, 60 tok session cap.

Expected behavior:
  1. Initial burst drains the bucket (chunks 1..4).
  2. Producer is then throttled to refill rate.
  3. Stream is cut off when session cap (60 tokens) is reached.
"""

from __future__ import annotations

import json

from limiter import StreamingTokenLimiter


def main() -> int:
    lim = StreamingTokenLimiter(
        capacity=20,
        tokens_per_sec=10.0,
        max_total_tokens=60,
    )

    # Producer wants to emit 5-token chunks back-to-back, indefinitely.
    # Caller respects whatever wait_s the limiter returns.
    chunk_size = 5
    t = 0.0
    chunks_emitted = 0
    waits_total = 0.0
    log = []

    for chunk_idx in range(20):  # try 20 chunks; cap will stop us first
        verdict, wait_s = lim.admit(chunk_size, t)
        if verdict == "wait":
            log.append({
                "chunk": chunk_idx,
                "t": round(t, 4),
                "verdict": "wait",
                "wait_s": round(wait_s, 4),
            })
            t += wait_s
            waits_total += wait_s
            verdict, wait_s = lim.admit(chunk_size, t)

        if verdict == "emit":
            chunks_emitted += 1
            log.append({
                "chunk": chunk_idx,
                "t": round(t, 4),
                "verdict": "emit",
                **lim.state(),
            })
        elif verdict == "stop":
            log.append({
                "chunk": chunk_idx,
                "t": round(t, 4),
                "verdict": "stop",
                **lim.state(),
            })
            break

    print("=== chunk-by-chunk trace ===")
    for row in log:
        print(json.dumps(row, sort_keys=True))

    print()
    print("=== summary ===")
    print(json.dumps({
        "chunks_emitted": chunks_emitted,
        "tokens_emitted": chunks_emitted * chunk_size,
        "wall_time_s": round(t, 4),
        "total_yield_s": round(waits_total, 4),
        "effective_rate_tok_per_s": round(
            (chunks_emitted * chunk_size) / t, 4
        ) if t > 0 else None,
        "final_state": lim.state(),
    }, sort_keys=True, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

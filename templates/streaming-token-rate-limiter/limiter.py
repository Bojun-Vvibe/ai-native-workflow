#!/usr/bin/env python3
"""Per-session streaming-token rate limiter with cooperative yield.

Caps the *output token rate* of a single streaming response so a runaway
generation cannot:
  - Exhaust a per-session output-token budget in one burst.
  - Starve sibling sessions sharing the same downstream sink (terminal,
    websocket, log shipper).
  - Outrun a downstream consumer (UI, TTS, captioner) that has its own
    sustainable consumption rate.

Pure stdlib. Deterministic: caller injects `now_s`. The limiter does not
sleep itself — it returns the `wait_s` the caller should yield for. This
makes it trivially testable AND usable from sync, threaded, OR asyncio
code (caller chooses how to yield).

Algorithm:
  - Per-session leaky-bucket / token-bucket hybrid.
  - `capacity` tokens (burst budget). Refill at `tokens_per_sec`.
  - Hard ceiling: `max_total_tokens` per session — once hit, the limiter
    refuses further chunks (signals end-of-stream to caller).

CLI:
    python limiter.py demo        # runs the worked example inline
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Tuple


@dataclass
class StreamingTokenLimiter:
    capacity: float                  # burst tokens
    tokens_per_sec: float            # sustained rate
    max_total_tokens: int            # hard session cap
    _tokens: float = field(init=False)
    _last_refill_s: float = field(init=False, default=0.0)
    _emitted_total: int = field(init=False, default=0)
    _initialized: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        if self.tokens_per_sec <= 0:
            raise ValueError("tokens_per_sec must be > 0")
        if self.max_total_tokens <= 0:
            raise ValueError("max_total_tokens must be > 0")
        self._tokens = float(self.capacity)

    def _refill(self, now_s: float) -> None:
        if not self._initialized:
            self._last_refill_s = now_s
            self._initialized = True
            return
        elapsed = max(0.0, now_s - self._last_refill_s)
        self._tokens = min(
            self.capacity,
            self._tokens + elapsed * self.tokens_per_sec,
        )
        self._last_refill_s = now_s

    def admit(self, n_tokens: int, now_s: float) -> Tuple[str, float]:
        """Try to admit a chunk of `n_tokens` output tokens.

        Returns (verdict, wait_s):
          ('emit',  0.0)       -> caller may emit chunk now.
          ('wait',  s)         -> caller must yield s seconds, then retry.
          ('stop',  0.0)       -> session cap reached; caller MUST end stream.

        On 'emit', tokens are debited and emitted_total is bumped.
        On 'wait' / 'stop', NO state mutation other than refill.
        """
        if n_tokens <= 0:
            raise ValueError("n_tokens must be > 0")
        self._refill(now_s)

        # Hard session cap check first — even if we have bucket tokens,
        # we refuse anything that would cross max_total_tokens.
        if self._emitted_total >= self.max_total_tokens:
            return ("stop", 0.0)
        if self._emitted_total + n_tokens > self.max_total_tokens:
            return ("stop", 0.0)

        if self._tokens >= n_tokens:
            self._tokens -= n_tokens
            self._emitted_total += n_tokens
            return ("emit", 0.0)

        deficit = n_tokens - self._tokens
        wait_s = deficit / self.tokens_per_sec
        return ("wait", wait_s)

    def state(self) -> dict:
        return {
            "tokens_available": round(self._tokens, 6),
            "emitted_total": self._emitted_total,
            "remaining_session_budget": self.max_total_tokens - self._emitted_total,
            "capped": self._emitted_total >= self.max_total_tokens,
        }


def _demo() -> int:
    lim = StreamingTokenLimiter(
        capacity=20,
        tokens_per_sec=10.0,
        max_total_tokens=60,
    )
    # Simulated stream: producer wants to emit 5-token chunks every 0.1s.
    # Bucket holds 20 burst, refill 10/s. So sustainable is 10/s; producer
    # wants 50/s. We expect cooperative throttling.
    arrivals = [(i * 0.1, 5) for i in range(15)]  # 15 chunks @ 5 tok = 75 tok desired
    log = []
    t = 0.0
    pending: list = list(arrivals)
    while pending:
        when, n = pending[0]
        # Caller has yielded until at least `when`.
        if t < when:
            t = when
        verdict, wait_s = lim.admit(n, t)
        if verdict == "emit":
            log.append({"t": round(t, 4), "n": n, "verdict": "emit", **lim.state()})
            pending.pop(0)
        elif verdict == "wait":
            log.append({"t": round(t, 4), "n": n, "verdict": "wait", "wait_s": round(wait_s, 4), **lim.state()})
            t += wait_s
        else:  # stop
            log.append({"t": round(t, 4), "n": n, "verdict": "stop", **lim.state()})
            break
    for row in log:
        print(json.dumps(row, sort_keys=True))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] == "demo":
        return _demo()
    print("usage: python limiter.py demo", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

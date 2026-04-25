"""
worked_example.py — streaming-token-rate-meter end-to-end.

Three scenarios in one run:

  1. Healthy stream: TTFT 0.10s, ~50 tok/s sustained for 2s. Snapshot
     mid-flight shows window_tokens_per_s near 50, is_stalled=False.
  2. Slow-start then accelerate: a long TTFT of 1.5s (cold backend),
     then a burst that the sliding window picks up while the cumulative
     rate stays low. Demonstrates why the window matters: the caller
     would see "fast NOW" even though "fast OVERALL" is false.
  3. Stall mid-flight: stream goes silent past stall_threshold_s; the
     meter flips is_stalled=True without any new chunk arriving, so
     a watchdog can cancel even when the upstream is wedged in
     `recv()` and producing no events at all.

Run: python3 worked_example.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from meter import StreamingTokenRateMeter  # noqa: E402


def _print(label: str, snap) -> None:
    d = asdict(snap)
    print(f"  {label:>32s}  {json.dumps(d, sort_keys=True)}")


def scenario_healthy() -> None:
    print("=" * 72)
    print("SCENARIO 1: healthy ~50 tok/s stream, TTFT=0.10s")
    print("=" * 72)
    m = StreamingTokenRateMeter(window_s=1.0, stall_threshold_s=2.0, now=lambda: 0.0)
    t0 = 100.0
    m.start(at_s=t0)
    # first chunk at t0+0.10s, 5 tokens; then every 0.10s another 5 tokens
    # for 2 seconds total => 50 tok/s steady
    for i in range(20):
        t = t0 + 0.10 + i * 0.10
        m.observe(now_s=t, tokens_delta=5)
    snap = m.snapshot(now_s=t0 + 2.10)
    _print("after 20 chunks (t=+2.10s)", snap)
    assert snap.ttft_s == 0.10, snap.ttft_s
    assert snap.total_tokens == 100
    assert 49.0 <= snap.window_tokens_per_s <= 51.0, snap.window_tokens_per_s
    assert snap.is_stalled is False
    print("  -> OK: TTFT 0.10s, 100 tokens, ~50 tok/s in last 1.0s")
    print()


def scenario_burst_after_slow_ttft() -> None:
    print("=" * 72)
    print("SCENARIO 2: cold-start TTFT=1.5s, then a burst — window vs cumulative")
    print("=" * 72)
    m = StreamingTokenRateMeter(window_s=1.0, stall_threshold_s=2.0, now=lambda: 0.0)
    t0 = 200.0
    m.start(at_s=t0)
    # TTFT = 1.5s (one chunk, 1 token)
    m.observe(now_s=t0 + 1.50, tokens_delta=1)
    snap_after_ttft = m.snapshot(now_s=t0 + 1.50)
    _print("right after first chunk", snap_after_ttft)
    assert snap_after_ttft.ttft_s == 1.50
    # then a burst of 80 tokens spread evenly over the next 1.0s
    for i in range(40):
        t = t0 + 1.50 + 0.025 * (i + 1)
        m.observe(now_s=t, tokens_delta=2)
    snap_burst = m.snapshot(now_s=t0 + 2.50)
    _print("end of burst (t=+2.50s)", snap_burst)
    assert snap_burst.total_tokens == 81
    # window should be ~80 tok/s (the burst), cumulative should be 81/2.50 ~= 32.4
    assert 75.0 <= snap_burst.window_tokens_per_s <= 85.0, snap_burst.window_tokens_per_s
    assert 30.0 <= snap_burst.cumulative_tokens_per_s <= 35.0, snap_burst.cumulative_tokens_per_s
    print("  -> OK: window=~80 tok/s (current), cumulative=~32 tok/s (whole-run)")
    print("     A caller that only logs cumulative would miss the burst.")
    print()


def scenario_stall() -> None:
    print("=" * 72)
    print("SCENARIO 3: stall detected without any new chunk arriving")
    print("=" * 72)
    m = StreamingTokenRateMeter(window_s=1.0, stall_threshold_s=2.0, now=lambda: 0.0)
    t0 = 300.0
    m.start(at_s=t0)
    # 5 chunks, then silence
    for i in range(5):
        m.observe(now_s=t0 + 0.10 + i * 0.10, tokens_delta=4)
    last_chunk_at = t0 + 0.50

    # snapshot 1.0s after last chunk: under stall threshold (2.0s) => not stalled
    snap_a = m.snapshot(now_s=last_chunk_at + 1.5)
    _print("1.5s after last chunk", snap_a)
    assert snap_a.is_stalled is False
    # window has aged out the most recent sample (last at +0.50, snapshot
    # at +2.00, window=1.0 -> cutoff=1.00, samples<1.00 evicted)
    assert snap_a.window_tokens_per_s == 0.0, snap_a.window_tokens_per_s

    # snapshot 2.5s after last chunk: past stall threshold => stalled
    snap_b = m.snapshot(now_s=last_chunk_at + 2.5)
    _print("2.5s after last chunk", snap_b)
    assert snap_b.is_stalled is True, snap_b
    print("  -> OK: meter flipped is_stalled=True with NO new chunk needed.")
    print("     A watchdog can cancel the upstream call from the snapshot alone.")
    print()


def main() -> int:
    scenario_healthy()
    scenario_burst_after_slow_ttft()
    scenario_stall()
    print("=" * 72)
    print("ALL SCENARIOS PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())

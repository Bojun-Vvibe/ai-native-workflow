"""Simulated 60-token stream with bursty arrivals.

Compares raw flush count (1 per token) vs debounced flush count.
Uses a fake clock so the demo is deterministic and runs in milliseconds.
"""

from debouncer import StreamDebouncer

# Fake clock — advanced by each chunk's inter-arrival delay.
_clock = [0.0]
def now() -> float:
    return _clock[0]


# 60 tokens with bursty arrivals (in seconds between tokens).
# Pattern: 10 quick (5ms apart), 50ms gap, 10 quick, 100ms gap, 30 quick, 200ms gap, 10 quick.
def build_stream() -> list[tuple[float, str]]:
    stream: list[tuple[float, str]] = []
    idx = 0
    def burst(n: int, gap: float):
        nonlocal idx
        for _ in range(n):
            stream.append((gap, f"tok{idx:02d} "))
            idx += 1
    burst(10, 0.005)
    stream.append((0.050, stream.pop()[1] if False else stream[-1][1]))  # noop, keeps shape
    # restructure properly: insert big gap before next burst
    stream2: list[tuple[float, str]] = []
    idx = 0
    def append_burst(n: int, intra_gap: float, lead_gap: float):
        nonlocal idx
        for i in range(n):
            gap = lead_gap if i == 0 else intra_gap
            stream2.append((gap, f"tok{idx:02d} "))
            idx += 1
    append_burst(10, 0.005, 0.000)
    append_burst(10, 0.005, 0.060)
    append_burst(30, 0.005, 0.120)
    append_burst(10, 0.005, 0.220)
    return stream2


def main() -> None:
    stream = build_stream()
    print("=" * 60)
    print("streaming-output-debouncer — worked example")
    print(f"Total tokens: {len(stream)}")
    print("=" * 60)

    deb = StreamDebouncer(min_interval_s=0.050, max_buffer_chars=64, now=now)
    flushes = []
    raw_flushes = 0

    for delay, chunk in stream:
        _clock[0] += delay
        raw_flushes += 1  # naive: 1 flush per token
        ev = deb.feed(chunk)
        if ev is not None:
            flushes.append(ev)
    final = deb.flush_final()
    if final is not None:
        flushes.append(final)

    print(f"\nRaw flush count (1-per-token): {raw_flushes}")
    print(f"Debounced flush count:         {len(flushes)}")
    print(f"Reduction:                     {raw_flushes - len(flushes)} fewer flushes "
          f"({100 * (raw_flushes - len(flushes)) / raw_flushes:.0f}%)")

    print("\nFlush events:")
    for i, ev in enumerate(flushes, 1):
        preview = ev.payload[:40] + ("…" if len(ev.payload) > 40 else "")
        print(f"  #{i:02d} t={ev.at*1000:6.1f}ms  reason={ev.reason:8s}  "
              f"chunks={ev.chunks:2d}  bytes={len(ev.payload):3d}  '{preview}'")

    print("\n" + "=" * 60)
    by_reason = {}
    for ev in flushes:
        by_reason[ev.reason] = by_reason.get(ev.reason, 0) + 1
    print(f"Flushes by reason: {by_reason}")
    print("=" * 60)


if __name__ == "__main__":
    main()

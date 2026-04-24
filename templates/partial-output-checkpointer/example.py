"""Worked example for partial-output-checkpointer.

Three scenarios:
  1. Stream a 1200-byte payload through a checkpointer with
     every_bytes=400; observe 3 policy-flushes + 1 finalize-flush,
     and a final SHA-256 over the whole stream.
  2. Simulate a host crash mid-flush by truncating the trailing log
     line; recover() reports a torn trailing record and resumes from
     the previous good checkpoint.
  3. Detect a corrupt log (non-trailing torn record) and refuse to
     recover.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from checkpointer import Checkpointer, CheckpointError, FlushPolicy, recover


class FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def main() -> None:
    print("== part 1: stream 1200 bytes, every_bytes=400, every_seconds=10 ==")
    sink = bytearray()
    log_lines: list[str] = []
    clock = FakeClock(2000.0)
    cp = Checkpointer(
        stream_id="render-job-7",
        policy=FlushPolicy(every_bytes=400, every_seconds=10.0),
        sink_write=sink.extend,
        log_write=log_lines.append,
        now_fn=clock,
    )

    # Five 240-byte chunks = 1200 bytes total.
    for i in range(5):
        chunk = (f"chunk-{i:02d}:" + "x" * 231).encode("ascii")
        assert len(chunk) == 240, len(chunk)
        flushed = cp.append(chunk)
        clock.advance(0.5)
        print(f"  append chunk-{i:02d} (240 B): "
              f"buffered={cp.state()['bytes_buffered']:>3} "
              f"committed={cp.state()['bytes_committed']:>4} "
              f"flushed_now={flushed}")

    summary = cp.finalize()
    print(f"finalize: bytes_committed={summary['bytes_committed']} "
          f"checkpoints={summary['checkpoints']} "
          f"final_sha256={summary['final_sha256'][:16]}...")
    print(f"sink length matches: {len(sink) == summary['bytes_committed']}")
    direct_sha = hashlib.sha256(bytes(sink)).hexdigest()
    print(f"final_sha256 matches direct hash of sink: {direct_sha == summary['final_sha256']}")

    print()
    print("== part 2: simulate crash by truncating last log line, then recover ==")
    full_log = "".join(log_lines)
    # Drop the trailing newline and clip half the last record => torn write.
    intact_log = "".join(log_lines[:-1])
    last = log_lines[-1].rstrip("\n")
    torn_log = intact_log + last[: len(last) // 2]  # no trailing newline either
    plan = recover(torn_log, expected_stream_id="render-job-7")
    print(f"intact_records={plan.intact_records} "
          f"torn_trailing_record={plan.torn_trailing_record}")
    print(f"resume bytes_committed={plan.bytes_committed} "
          f"running_sha256={plan.last_running_sha256[:16]}...")
    # Caller would now: open sink, seek to plan.bytes_committed, verify
    # hash matches, then resume the stream from byte plan.bytes_committed.
    sink_prefix = bytes(sink)[: plan.bytes_committed]
    print(f"verify on disk: sha256(sink[:{plan.bytes_committed}]) == last_running_sha256? "
          f"{hashlib.sha256(sink_prefix).hexdigest() == plan.last_running_sha256}")

    print()
    print("== part 3: clean recover from full intact log ==")
    plan2 = recover(full_log, expected_stream_id="render-job-7")
    print(f"intact_records={plan2.intact_records} "
          f"torn_trailing_record={plan2.torn_trailing_record} "
          f"bytes_committed={plan2.bytes_committed}")

    print()
    print("== part 4: corrupt non-trailing record is rejected loudly ==")
    bad_log = log_lines[0] + "{not json\n" + log_lines[1]
    try:
        recover(bad_log, expected_stream_id="render-job-7")
    except CheckpointError as e:
        print(f"CheckpointError raised as expected: {e}")

    print()
    print("== part 5: append-after-finalize is rejected ==")
    try:
        cp.append(b"late")
    except CheckpointError as e:
        print(f"CheckpointError raised as expected: {e}")


if __name__ == "__main__":
    main()

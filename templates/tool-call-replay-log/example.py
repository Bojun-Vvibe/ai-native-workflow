"""Worked example for tool-call-replay-log.

Five parts:
  1. Record three tool calls into a fresh log.
  2. Verify the hash chain.
  3. Replay them in order.
  4. Prove a drifted arg raises ReplayMiss.
  5. Prove tamper detection: corrupt one byte, verify() catches it.
"""

from __future__ import annotations

import os
import tempfile

from replay_log import ReplayLog, ReplayMiss, CanonicalizationError, canonical_key


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="replaylog-")
    log_path = os.path.join(tmpdir, "session.jsonl")
    log = ReplayLog(log_path)

    print("=" * 70)
    print("PART 1: record three calls")
    print("=" * 70)

    rec1 = log.record_call(
        tool="read_file",
        args={"path": "/etc/hosts", "encoding": "utf-8"},
        result={"bytes": 220, "first_line": "127.0.0.1 localhost"},
        status="ok",
        started_at=1700000000.0,
        finished_at=1700000000.012,
        attempt_id="call-001",
        identity_fields=["path", "encoding"],
    )
    rec2 = log.record_call(
        tool="list_files",
        args={"dir": "/tmp", "glob": "*.log"},
        result={"matches": ["a.log", "b.log"]},
        status="ok",
        started_at=1700000001.0,
        finished_at=1700000001.030,
        attempt_id="call-002",
        identity_fields=["dir", "glob"],
    )
    # Same logical key as rec1 but different volatile metadata (request_id is NOT
    # in identity_fields). Should still produce same canonical_key.
    rec3 = log.record_call(
        tool="read_file",
        args={"encoding": "utf-8", "path": "/etc/hosts", "request_id": "req-xyz"},
        result={"bytes": 220, "first_line": "127.0.0.1 localhost"},
        status="ok",
        started_at=1700000002.0,
        finished_at=1700000002.011,
        attempt_id="call-003",
        identity_fields=["path", "encoding"],
    )
    print(f"  recorded seq=0..2, prev_hash chain head: {rec3['record_hash'][:16]}...")
    assert rec1["canonical_key"] == rec3["canonical_key"], "dict-order/volatile-arg leak"
    print(f"  rec1.canonical_key == rec3.canonical_key (dict-order + volatile-arg invariant): OK")

    print()
    print("=" * 70)
    print("PART 2: verify chain")
    print("=" * 70)
    n, ok, bad = log.verify()
    print(f"  verify -> records_checked={n}, ok={ok}, first_bad_seq={bad}")
    assert n == 3 and ok and bad is None

    print()
    print("=" * 70)
    print("PART 3: replay in recorded order")
    print("=" * 70)
    r1 = log.replay("read_file", {"path": "/etc/hosts", "encoding": "utf-8"}, identity_fields=["path", "encoding"])
    print(f"  replay #1 read_file(/etc/hosts) -> {r1}")
    r2 = log.replay("list_files", {"dir": "/tmp", "glob": "*.log"}, identity_fields=["dir", "glob"])
    print(f"  replay #2 list_files          -> {r2}")
    # Same key as r1 — second occurrence (rec3) should come back, NOT rec1 again.
    r3 = log.replay("read_file", {"path": "/etc/hosts", "encoding": "utf-8"}, identity_fields=["path", "encoding"])
    print(f"  replay #3 read_file(/etc/hosts) -> {r3} (consumed second recording)")
    assert r1 == rec1["result"] and r3 == rec3["result"]

    print()
    print("=" * 70)
    print("PART 4: drifted arg -> ReplayMiss")
    print("=" * 70)
    try:
        log.replay("read_file", {"path": "/etc/passwd", "encoding": "utf-8"}, identity_fields=["path", "encoding"])
        print("  FAIL: expected ReplayMiss"); return 1
    except ReplayMiss as e:
        print(f"  ReplayMiss raised as expected: {str(e)[:80]}")

    # Float in identity args is rejected loudly.
    try:
        canonical_key("foo", {"x": 0.1}, identity_fields=["x"])
        print("  FAIL: expected CanonicalizationError"); return 1
    except CanonicalizationError as e:
        print(f"  CanonicalizationError on float arg: {str(e)[:80]}")

    print()
    print("=" * 70)
    print("PART 5: tamper detection")
    print("=" * 70)
    # Read all lines, flip a byte in the middle of seq=1's result.
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    tampered = lines[1].replace('"a.log"', '"X.log"')
    lines[1] = tampered
    with open(log_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    n, ok, bad = log.verify()
    print(f"  after tamper: verify -> records_checked={n}, ok={ok}, first_bad_seq={bad}")
    assert ok is False and bad == 1, f"tamper not detected (n={n}, ok={ok}, bad={bad})"

    print()
    print("ALL PARTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

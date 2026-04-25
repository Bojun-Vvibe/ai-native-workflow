"""Worked example: incremental hashing with explicit finalization.

Five scenarios:
  1. Happy path: feed all chunks, finalize, get the same digest as a one-shot
     hashlib.sha256 over the concatenation.
  2. Mid-stream digest is None — proves the API never hands out a partial hash.
  3. Idempotent finalize — calling finalize() twice returns the same string.
  4. Late chunk after finalize — raises StreamClosedError.
  5. Aborted stream — digest stays None, finalize raises StreamAbortedError.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from template import (  # noqa: E402
    ChecksumFinalizer,
    StreamAbortedError,
    StreamClosedError,
)


def case_happy_path() -> None:
    print("=== happy path: digest matches one-shot hashlib over concat ===")
    chunks = [b"the quick ", b"brown fox ", b"jumps over ", b"the lazy dog"]
    cf = ChecksumFinalizer("sha256")
    for c in chunks:
        cf.feed(c)
    final_hex = cf.finalize()
    expected = hashlib.sha256(b"".join(chunks)).hexdigest()
    print(f"  bytes_seen   = {cf.bytes_seen}")
    print(f"  finalize()   = {final_hex}")
    print(f"  expected     = {expected}")
    print(f"  match        = {final_hex == expected}")
    assert final_hex == expected
    assert cf.bytes_seen == sum(len(c) for c in chunks)
    print()


def case_mid_stream_digest_is_none() -> None:
    print("=== mid-stream digest is None (no partial leak) ===")
    cf = ChecksumFinalizer()
    cf.feed(b"partial-")
    print(f"  after 1 feed:  digest={cf.digest}  hexdigest={cf.hexdigest}  closed={cf.closed}")
    cf.feed(b"input")
    print(f"  after 2 feeds: digest={cf.digest}  hexdigest={cf.hexdigest}  closed={cf.closed}")
    h = cf.finalize()
    print(f"  after finalize: hexdigest={h[:16]}...  closed={cf.closed}")
    assert cf.digest is not None
    assert cf.hexdigest is not None
    print()


def case_finalize_is_idempotent() -> None:
    print("=== finalize() is idempotent ===")
    cf = ChecksumFinalizer()
    cf.feed(b"hello world")
    a = cf.finalize()
    b = cf.finalize()
    print(f"  first  = {a}")
    print(f"  second = {b}")
    print(f"  same?  = {a == b}")
    assert a == b
    print()


def case_late_chunk_rejected() -> None:
    print("=== feed() after finalize() raises StreamClosedError ===")
    cf = ChecksumFinalizer()
    cf.feed(b"first half ")
    cf.finalize()
    try:
        cf.feed(b"sneaky late chunk")
    except StreamClosedError as e:
        print(f"  rejected: {e}")
    else:
        raise AssertionError("expected StreamClosedError")
    print()


def case_abort_poisons_stream() -> None:
    print("=== abort() poisons the stream ===")
    cf = ChecksumFinalizer()
    cf.feed(b"chunk-1 ")
    cf.feed(b"chunk-2 ")
    cf.abort()
    print(f"  after abort: digest={cf.digest}  hexdigest={cf.hexdigest}  aborted={cf.aborted}")
    try:
        cf.finalize()
    except StreamAbortedError as e:
        print(f"  finalize rejected: {e}")
    try:
        cf.feed(b"more")
    except StreamAbortedError as e:
        print(f"  feed rejected:     {e}")
    print()


def main() -> int:
    case_happy_path()
    case_mid_stream_digest_is_none()
    case_finalize_is_idempotent()
    case_late_chunk_rejected()
    case_abort_poisons_stream()
    print("all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

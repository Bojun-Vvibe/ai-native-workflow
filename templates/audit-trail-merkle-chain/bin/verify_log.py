"""CLI: verify a merkle log file.

Usage:
    python3 verify_log.py <log_path> [<expected_head_hash>]

Prints one summary line; exits 0 on ok, 1 on tamper.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from merkle_log import verify  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_log.py <path> [expected_head_hash]")
        return 2
    path = sys.argv[1]
    expected = sys.argv[2] if len(sys.argv) > 2 else None
    result = verify(path, expected_head_hash=expected)
    if result["ok"]:
        print(f"ok entries={result['entries_verified']} head={result['head_hash'][:16]}")
        return 0
    print(
        f"BROKEN at_index={result['broken_at_index']} reason={result['reason']} "
        f"detail={result['detail']}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""Example 2: persistent gap + inconsistent-payload duplicate.

Three chunks arrive but seq=1 never does. State reports the gap
explicitly so the caller can decide to give up. Then a duplicate of
seq=2 with a *different* payload arrives — the reassembler refuses it
loudly via InconsistentChunk, so two flapping upstream replicas can't
silently corrupt the stream.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reassembler import InconsistentChunk, StreamReassembler


def main() -> int:
    r = StreamReassembler()

    # seq=0 arrives, gets delivered immediately.
    out = r.accept({"seq": 0, "data": "alpha-", "is_final": False})
    print(f"after seq=0: delivered={[d['seq'] for d in out]} "
          f"state={json.dumps(r.state(), sort_keys=True)}")

    # seq=2 arrives early; nothing delivered, gap=[1] reported.
    out = r.accept({"seq": 2, "data": "gamma-", "is_final": False})
    print(f"after seq=2: delivered={[d['seq'] for d in out]} "
          f"state={json.dumps(r.state(), sort_keys=True)}")

    # seq=3 arrives, marked is_final; still blocked by gap.
    out = r.accept({"seq": 3, "data": "delta.", "is_final": True})
    print(f"after seq=3: delivered={[d['seq'] for d in out]} "
          f"state={json.dumps(r.state(), sort_keys=True)}")

    print()
    print(f"caller observes persistent gap: {r.gap_seqs()}")
    print(f"is_complete (should be False, gap=[1]): {r.is_complete()}")

    # A flapping upstream replica re-sends seq=2 with a *different*
    # payload. We must refuse — silently overwriting would corrupt
    # the stream.
    print()
    print("attempting to accept duplicate seq=2 with different payload...")
    try:
        r.accept({"seq": 2, "data": "GAMMA-DIFFERENT", "is_final": False})
    except InconsistentChunk as e:
        print(f"InconsistentChunk raised as expected: {e}")

    # Idempotent duplicate (same payload) is silently accepted.
    print()
    print("re-sending seq=2 with the ORIGINAL payload (idempotent)...")
    out = r.accept({"seq": 2, "data": "gamma-", "is_final": False})
    print(f"delivered={[d['seq'] for d in out]} (must be empty: already buffered)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

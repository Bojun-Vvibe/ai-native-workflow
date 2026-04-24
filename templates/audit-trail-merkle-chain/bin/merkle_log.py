"""Stdlib-only append + verify for an audit-trail merkle chain.

Clock is injected for determinism. File is plain JSONL.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

GENESIS_PREV = "0" * 64


def canonical(entry_without_hash: Dict[str, Any]) -> str:
    return json.dumps(entry_without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_entry(entry_without_hash: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical(entry_without_hash).encode("utf-8")).hexdigest()


@dataclass
class AppendResult:
    index: int
    entry_hash: str


class MerkleLog:
    def __init__(self, path: str, clock: Callable[[], str]) -> None:
        """`clock` returns an RFC3339 UTC string."""
        self.path = path
        self.clock = clock

    def _read_last(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            return None
        last_line = None
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last_line = line
        if last_line is None:
            return None
        return json.loads(last_line)

    def append(self, payload: Any) -> AppendResult:
        last = self._read_last()
        if last is None:
            index = 0
            prev_hash = GENESIS_PREV
        else:
            index = int(last["index"]) + 1
            prev_hash = last["entry_hash"]

        body = {
            "index": index,
            "ts": self.clock(),
            "prev_hash": prev_hash,
            "payload": payload,
        }
        eh = hash_entry(body)
        full = dict(body)
        full["entry_hash"] = eh

        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(full, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
        return AppendResult(index=index, entry_hash=eh)

    def head_hash(self) -> Optional[str]:
        last = self._read_last()
        return last["entry_hash"] if last else None


def verify(path: str, expected_head_hash: Optional[str] = None) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"ok": False, "broken_at_index": 0, "reason": "missing", "detail": {"path": path}}

    prev_hash = GENESIS_PREV
    count = 0
    last_eh: Optional[str] = None

    with open(path, "r", encoding="utf-8") as fh:
        for i, raw in enumerate(fh):
            raw = raw.rstrip("\n")
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as exc:
                return {"ok": False, "broken_at_index": i, "reason": "parse", "detail": {"error": str(exc)}}

            if entry.get("index") != i:
                return {
                    "ok": False,
                    "broken_at_index": i,
                    "reason": "index_gap",
                    "detail": {"expected": i, "got": entry.get("index")},
                }

            if entry.get("prev_hash") != prev_hash:
                return {
                    "ok": False,
                    "broken_at_index": i,
                    "reason": "prev_hash_mismatch",
                    "detail": {"expected_prev": prev_hash, "got_prev": entry.get("prev_hash")},
                }

            stored_eh = entry.get("entry_hash")
            body = {k: v for k, v in entry.items() if k != "entry_hash"}
            recomputed = hash_entry(body)
            if recomputed != stored_eh:
                return {
                    "ok": False,
                    "broken_at_index": i,
                    "reason": "entry_hash_mismatch",
                    "detail": {"stored": stored_eh, "recomputed": recomputed},
                }

            prev_hash = stored_eh
            last_eh = stored_eh
            count += 1

    if expected_head_hash is not None and last_eh != expected_head_hash:
        return {
            "ok": False,
            "broken_at_index": count - 1 if count else 0,
            "reason": "head_mismatch",
            "detail": {"expected_head": expected_head_hash, "got_head": last_eh},
        }

    return {"ok": True, "entries_verified": count, "head_hash": last_eh or GENESIS_PREV}

"""Append-only, hash-chained tool-call replay log.

Stdlib-only. Single-host single-writer-per-file is the supported mode; concurrent
appenders on one host work because each record is one O_APPEND write below
PIPE_BUF. Cross-host concurrent writers are out of scope.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Iterable

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class ReplayLogError(Exception):
    """Base class."""


class CanonicalizationError(ReplayLogError):
    """Args contained a value that cannot be canonicalized (e.g. float)."""


class ReplayMiss(ReplayLogError):
    """No recorded result matches (tool, canonical(args)) at this point."""


class ChainBroken(ReplayLogError):
    """verify() found a bad prev_hash or unparseable record."""


def _canonical(value: Any, pointer: str = "") -> Any:
    """Recursive canonicalization. Floats raise — silent precision is a trap."""
    if isinstance(value, float):
        raise CanonicalizationError(
            f"float at {pointer or '/'} is not allowed in identity args; "
            f"use a string with explicit precision or an int"
        )
    if isinstance(value, dict):
        return {k: _canonical(v, f"{pointer}/{k}") for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v, f"{pointer}/{i}") for i, v in enumerate(value)]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise CanonicalizationError(
        f"unsupported type {type(value).__name__} at {pointer or '/'}"
    )


def canonical_key(tool: str, args: dict, identity_fields: Iterable[str] | None = None) -> str:
    """Stable hashable key for (tool, identity_args)."""
    if identity_fields is not None:
        args = {k: args[k] for k in identity_fields if k in args}
    canon = _canonical(args)
    blob = json.dumps({"tool": tool, "args": canon}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _record_hash(prev_hash: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(b"\n")
    h.update(body.encode("utf-8"))
    return h.hexdigest()


class ReplayLog:
    def __init__(self, path: str):
        self.path = path
        # In-memory replay cursor: maps canonical_key -> next index into recorded list.
        self._cursors: dict[str, int] = {}
        self._by_key: dict[str, list[dict]] | None = None  # lazy-loaded for replay

    # ---- record path -----------------------------------------------------

    def _last_hash(self) -> str:
        if not os.path.exists(self.path):
            return EMPTY_SHA256
        last = EMPTY_SHA256
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                last = rec["record_hash"]
        return last

    def record_call(
        self,
        tool: str,
        args: dict,
        result: Any,
        *,
        status: str,
        started_at: float,
        finished_at: float,
        attempt_id: str,
        identity_fields: Iterable[str] | None = None,
    ) -> dict:
        prev = self._last_hash()
        seq = self._next_seq()
        canon_args = _canonical(args)
        ck = canonical_key(tool, args, identity_fields)
        payload = {
            "seq": seq,
            "tool": tool,
            "args": canon_args,
            "canonical_key": ck,
            "result": result,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "attempt_id": attempt_id,
            "prev_hash": prev,
        }
        rh = _record_hash(prev, payload)
        record = dict(payload)
        record["record_hash"] = rh
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        # O_APPEND ensures atomic interleaving across processes for sub-PIPE_BUF writes.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        # Invalidate replay index since the file changed.
        self._by_key = None
        return record

    def _next_seq(self) -> int:
        if not os.path.exists(self.path):
            return 0
        with open(self.path, "r", encoding="utf-8") as f:
            n = sum(1 for line in f if line.strip())
        return n

    # ---- replay path -----------------------------------------------------

    def _load_index(self) -> None:
        index: dict[str, list[dict]] = {}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        # Torn trailing line — verify() will catch it. Skip for replay.
                        continue
                    index.setdefault(rec["canonical_key"], []).append(rec)
        self._by_key = index

    def replay(self, tool: str, args: dict, identity_fields: Iterable[str] | None = None) -> Any:
        if self._by_key is None:
            self._load_index()
        ck = canonical_key(tool, args, identity_fields)
        bucket = self._by_key.get(ck, [])  # type: ignore[union-attr]
        cursor = self._cursors.get(ck, 0)
        if cursor >= len(bucket):
            raise ReplayMiss(f"no recorded result for tool={tool!r} key={ck} (cursor={cursor}, recorded={len(bucket)})")
        rec = bucket[cursor]
        self._cursors[ck] = cursor + 1
        return rec["result"]

    def reset_cursors(self) -> None:
        self._cursors.clear()

    # ---- verification ----------------------------------------------------

    def verify(self) -> tuple[int, bool, int | None]:
        """Re-walk the chain. Returns (records_checked, ok, first_bad_seq)."""
        if not os.path.exists(self.path):
            return (0, True, None)
        prev = EMPTY_SHA256
        n = 0
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, raw in enumerate(lines):
            raw = raw.rstrip("\n")
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                # Torn trailing line is tolerated only at the very end.
                if i == len(lines) - 1:
                    return (n, True, None)
                return (n, False, n)
            if rec.get("prev_hash") != prev:
                return (n, False, rec.get("seq"))
            payload = {k: v for k, v in rec.items() if k != "record_hash"}
            expected = _record_hash(prev, payload)
            if expected != rec.get("record_hash"):
                return (n, False, rec.get("seq"))
            prev = rec["record_hash"]
            n += 1
        return (n, True, None)

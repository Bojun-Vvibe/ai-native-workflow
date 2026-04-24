"""Stdlib-only reference implementation of the idempotency-key protocol.

The store is a single JSON file on disk. Clock and storage path are
injected so tests are deterministic.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class IdempotencyConflict(Exception):
    def __init__(self, detail: Dict[str, Any]) -> None:
        super().__init__(f"idempotency conflict: {detail}")
        self.detail = detail


@dataclass
class StoreEntry:
    request_hash: str
    response: Any
    stored_at: float
    ttl_seconds: int

    def is_live(self, now: float) -> bool:
        return (now - self.stored_at) < self.ttl_seconds

    def to_json(self) -> Dict[str, Any]:
        return {
            "request_hash": self.request_hash,
            "response": self.response,
            "stored_at": self.stored_at,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_json(cls, blob: Dict[str, Any]) -> "StoreEntry":
        return cls(
            request_hash=blob["request_hash"],
            response=blob["response"],
            stored_at=float(blob["stored_at"]),
            ttl_seconds=int(blob["ttl_seconds"]),
        )


class IdempotencyStore:
    def __init__(self, path: str, clock: Callable[[], float]) -> None:
        self.path = path
        self.clock = clock

    # ---- internal I/O ----

    def _load(self) -> Dict[str, StoreEntry]:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k: StoreEntry.from_json(v) for k, v in raw.items()}

    def _save(self, entries: Dict[str, StoreEntry]) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({k: v.to_json() for k, v in entries.items()}, fh, sort_keys=True, indent=2)
        os.replace(tmp, self.path)

    # ---- public surface ----

    def call(
        self,
        key: str,
        request: Any,
        execute: Callable[[Any], Any],
        ttl_seconds: int = 86400,
    ) -> Dict[str, Any]:
        """Execute or dedupe a tool call.

        Returns a response envelope as defined in SPEC.md.
        Raises IdempotencyConflict on Rule 3.
        """
        if not key or not (1 <= len(key) <= 128):
            raise ValueError("idempotency_key must be 1..128 chars")

        now = self.clock()
        rhash = request_hash(request)
        entries = self._load()
        existing = entries.get(key)

        if existing is not None and existing.is_live(now):
            if existing.request_hash == rhash:
                return {
                    "idempotency_key": key,
                    "status": "replayed",
                    "response": existing.response,
                    "stored_at": existing.stored_at,
                }
            detail = {
                "expected_request_hash": existing.request_hash,
                "received_request_hash": rhash,
                "stored_at": existing.stored_at,
            }
            raise IdempotencyConflict(detail)

        # fresh (no entry, or expired)
        response = execute(request)
        entries[key] = StoreEntry(
            request_hash=rhash,
            response=response,
            stored_at=now,
            ttl_seconds=ttl_seconds,
        )
        self._save(entries)
        return {
            "idempotency_key": key,
            "status": "fresh",
            "response": response,
            "stored_at": now,
        }


def validate_envelope(envelope: Dict[str, Any]) -> Optional[str]:
    """Lightweight schema check. Returns None on ok, else error string."""
    required = {"idempotency_key", "request", "issued_at", "ttl_seconds"}
    missing = required - set(envelope.keys())
    if missing:
        return f"missing fields: {sorted(missing)}"
    key = envelope["idempotency_key"]
    if not isinstance(key, str) or not (1 <= len(key) <= 128):
        return "idempotency_key must be a string of length 1..128"
    if not isinstance(envelope["ttl_seconds"], int) or envelope["ttl_seconds"] <= 0:
        return "ttl_seconds must be a positive int"
    return None

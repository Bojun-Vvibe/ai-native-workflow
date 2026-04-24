"""Tool-call deduplication by call-signature hash.

Detects when an agent re-issues a tool call with the same effective
arguments — without requiring the caller to mint an idempotency key.
Returns the cached prior result instead of re-executing.

This is the *signature-based* sibling of `tool-call-retry-envelope`'s
explicit idempotency key:

- `tool-call-retry-envelope`: caller MUST mint an `idempotency_key`;
  works across process restarts; designed for at-least-once transport.
- `tool-call-deduplication` (this): caller mints nothing; the host
  hashes `(tool_name, canonical(args))` and dedups within a window.
  Designed for the case where a looping agent makes the same logical
  call twice in quick succession (e.g. confused by a partial trace).

API
---
- `dedup_key(tool_name, args, identity_fields=None)` -> str
  Canonical SHA-256 over `(tool_name, sorted(identity_args))`.
  If `identity_fields` is given, ONLY those keys participate in the
  hash; other fields (timestamps, request-ids, freeform comments)
  are ignored. This avoids the trap where a `now()` field defeats
  every dedup attempt.

- `DedupCache(window_seconds, now_fn)` -> instance
  In-memory cache. `now_fn()` MUST return a monotonic float. Inject
  it so tests are deterministic.

  - `lookup(key) -> dict | None`
    Returns the cached result envelope (with `cached_at`,
    `original_call_id`, `result`) if hit and not expired, else None.
    Expired entries are evicted on access.

  - `record(key, call_id, result)`
    Stores a result. Overwrites any prior (expired or live) entry for
    `key`.

  - `decide(tool_name, args, call_id, identity_fields=None)`
    Convenience: returns `{"verdict": "execute" | "use_cached",
    "key": <hex>, "cached": <envelope or None>}`. Caller branches:
    `execute` -> run the tool, then `record(...)`.
    `use_cached` -> return `cached["result"]` and log
    `original_call_id` for the audit trail.

  - `state()` -> dict (sorted keys), suitable for a heartbeat.

Invariants
----------
1. Two calls with byte-identical canonicalized identity-args hash to
   the same key.
2. Dict key order does NOT change the hash (canonical JSON).
3. Floats are forbidden in identity-args (silent precision loss is a
   correctness trap); raise `TypeError`. Use ints or string-encode
   if you really need a float.
4. `lookup` after `window_seconds` returns None and evicts the entry.
5. `record` is idempotent on the same `(key, call_id)` pair: repeated
   record with the SAME call_id is a no-op (no `cached_at` bump);
   repeated record with a DIFFERENT call_id refreshes the entry and
   updates `original_call_id`.

Out of scope
------------
- Cross-process persistence (use `tool-call-retry-envelope`'s SQLite
  table for that).
- Negative caching of failures (a failed call gets re-executed; this
  module only caches the result the caller passes to `record`).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable


class CanonicalizationError(TypeError):
    pass


def _canonicalize(value: Any, *, path: str = "$") -> Any:
    """Recursively validate and normalize a value for hashing.

    - Floats are rejected (silent precision loss).
    - Tuples are coerced to lists (JSON has no tuples).
    - dict keys must be strings.
    """
    if isinstance(value, bool):
        # bool is a subclass of int; check first to keep True/False stable.
        return value
    if value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        raise CanonicalizationError(
            f"float not allowed in identity-args at {path}: {value!r}. "
            "Use int or string-encode."
        )
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v, path=f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        out = {}
        for k in sorted(value.keys()):
            if not isinstance(k, str):
                raise CanonicalizationError(
                    f"dict key must be str at {path}: {k!r}"
                )
            out[k] = _canonicalize(value[k], path=f"{path}.{k}")
        return out
    raise CanonicalizationError(
        f"unsupported type {type(value).__name__} at {path}"
    )


def dedup_key(
    tool_name: str,
    args: dict[str, Any],
    identity_fields: list[str] | None = None,
) -> str:
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool_name must be a non-empty str")
    if not isinstance(args, dict):
        raise ValueError("args must be a dict")
    if identity_fields is not None:
        identity_args = {k: args[k] for k in identity_fields if k in args}
    else:
        identity_args = args
    canon = {
        "tool": tool_name,
        "args": _canonicalize(identity_args),
    }
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class DedupCache:
    def __init__(
        self,
        window_seconds: float,
        now_fn: Callable[[], float],
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._window = float(window_seconds)
        self._now_fn = now_fn
        # key -> {"cached_at": float, "original_call_id": str, "result": Any}
        self._store: dict[str, dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def lookup(self, key: str) -> dict[str, Any] | None:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        now = self._now_fn()
        if now - entry["cached_at"] > self._window:
            del self._store[key]
            self._evictions += 1
            self._misses += 1
            return None
        self._hits += 1
        # Return a shallow copy so callers can't mutate our store.
        return {
            "cached_at": entry["cached_at"],
            "original_call_id": entry["original_call_id"],
            "result": entry["result"],
        }

    def record(self, key: str, call_id: str, result: Any) -> None:
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("call_id must be a non-empty str")
        existing = self._store.get(key)
        if existing is not None and existing["original_call_id"] == call_id:
            # Idempotent: same call recording its own result twice.
            return
        self._store[key] = {
            "cached_at": self._now_fn(),
            "original_call_id": call_id,
            "result": result,
        }

    def decide(
        self,
        tool_name: str,
        args: dict[str, Any],
        call_id: str,
        identity_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        key = dedup_key(tool_name, args, identity_fields=identity_fields)
        cached = self.lookup(key)
        if cached is None:
            return {"verdict": "execute", "key": key, "cached": None}
        return {"verdict": "use_cached", "key": key, "cached": cached}

    def state(self) -> dict[str, Any]:
        # Evict expired entries lazily for an accurate count.
        now = self._now_fn()
        expired = [k for k, v in self._store.items()
                   if now - v["cached_at"] > self._window]
        for k in expired:
            del self._store[k]
            self._evictions += 1
        return {
            "entries": len(self._store),
            "evictions": self._evictions,
            "hits": self._hits,
            "misses": self._misses,
            "window_seconds": self._window,
        }

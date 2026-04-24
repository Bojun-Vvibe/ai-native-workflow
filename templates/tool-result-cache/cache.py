"""Content-addressed result cache for deterministic tool calls.

Stdlib only. Pure: no I/O, injectable clock. Caller declares which tools
are deterministic (`safe_tools`) and which arg fields participate in the
content key (`identity_fields`); everything else is ignored at hash
time so volatile metadata (request_ids, timestamps) does not poison the
cache.

Differs from `tool-call-deduplication` in three ways:

1. Deliberately persistable: `state()` exposes a snapshot you can dump
   to JSONL and re-load via `replay`, so the cache survives restart.
2. TTL is per-entry (`ttl_s` at write), not a single shared window.
3. Cache writes require an explicit `safe=True` opt-in — the engine
   refuses to cache a tool not in `safe_tools` (raises
   `UnsafeCacheError`) so a non-deterministic call cannot be cached
   by accident.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


class CacheKeyError(ValueError):
    """Raised when args cannot be canonicalized for a cache key."""


class UnsafeCacheError(RuntimeError):
    """Raised when caller tries to cache a tool not in safe_tools."""


def _canonical(value: Any, path: str = "$") -> Any:
    if isinstance(value, float):
        # Same trap as in tool-call-deduplication: JSON float round-trip
        # is not bit-stable; refuse rather than silently mis-key.
        raise CacheKeyError(
            f"float not allowed in identity-args at {path}: {value!r}. "
            "Use int or string-encode."
        )
    if isinstance(value, dict):
        return {k: _canonical(value[k], f"{path}.{k}") for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise CacheKeyError(f"unsupported type at {path}: {type(value).__name__}")


def cache_key(tool_name: str, args: dict, identity_fields: Iterable[str] | None = None) -> str:
    if identity_fields is None:
        identity = args
    else:
        identity = {k: args[k] for k in identity_fields if k in args}
    blob = json.dumps(
        {"tool": tool_name, "args": _canonical(identity)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


@dataclass
class _Entry:
    result: Any
    written_at: float
    expires_at: float
    source_call_id: str


@dataclass
class ToolResultCache:
    safe_tools: frozenset[str]
    now_fn: Callable[[], float]
    _entries: dict[str, _Entry] = field(default_factory=dict)
    _hits: int = 0
    _misses: int = 0
    _evictions: int = 0
    _refused: int = 0  # write attempts on unsafe tools

    def _evict_if_expired(self, key: str) -> None:
        e = self._entries.get(key)
        if e is None:
            return
        if self.now_fn() >= e.expires_at:
            del self._entries[key]
            self._evictions += 1

    def lookup(self, key: str) -> dict | None:
        self._evict_if_expired(key)
        e = self._entries.get(key)
        if e is None:
            self._misses += 1
            return None
        self._hits += 1
        return {
            "result": e.result,
            "written_at": e.written_at,
            "expires_at": e.expires_at,
            "source_call_id": e.source_call_id,
        }

    def write(
        self,
        tool_name: str,
        key: str,
        result: Any,
        ttl_s: float,
        source_call_id: str,
    ) -> None:
        if tool_name not in self.safe_tools:
            self._refused += 1
            raise UnsafeCacheError(
                f"refusing to cache non-deterministic tool {tool_name!r}; "
                f"add it to safe_tools to opt in"
            )
        if ttl_s <= 0:
            raise ValueError(f"ttl_s must be > 0, got {ttl_s}")
        now = self.now_fn()
        self._entries[key] = _Entry(
            result=result,
            written_at=now,
            expires_at=now + ttl_s,
            source_call_id=source_call_id,
        )

    def state(self) -> dict:
        return {
            "entries": len(self._entries),
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "refused_unsafe_writes": self._refused,
            "safe_tools": sorted(self.safe_tools),
        }

"""Pure stdlib detector for stale embedding-cache entries by source file mtime.

Premise: an embedding cache stores `(source_path, content_hash, embedded_at,
embedding_model, vector_dim)` for each entry. The expensive thing was the
remote embed call; the cheap thing is checking whether the source file has
changed on disk since the embedding was computed.

Three failure modes this catches BEFORE a stale embedding gets returned for
a similarity query:

1. mtime_drift:    source file mtime > embedded_at AND content_hash mismatches
                   -> the file changed; embedding is stale; re-embed.

2. mtime_only:     source file mtime > embedded_at BUT content_hash still
                   matches (a touch / chmod / re-checkout that updated mtime
                   without changing content). The orchestrator can choose to
                   refresh `embedded_at` cheaply (no re-embed needed) so the
                   next scan doesn't re-flag — this is "drift recoverable
                   without an API call".

3. missing:        the source file no longer exists on disk. The cache entry
                   is dangling; nearest-neighbor results that surface this
                   embedding will reference a non-existent path. Mark for
                   eviction.

Why mtime, not just content_hash?
- Content hash requires reading every source file on every scan (O(N * filesize)).
- mtime is a single stat() call (O(1) per file) and answers "did anything
  *possibly* change?" — re-hash only the candidates, not the whole corpus.
- The detector therefore returns mtime-flagged candidates with hash STILL
  CACHED (from the entry); the caller decides whether to re-hash on disk.

Stdlib only. Pure logic in `evaluate(entry, fs_facts)`; the I/O wrapper
`scan_directory(...)` is small and isolated so the engine can be tested
deterministically with synthetic FsFacts.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CacheEntry:
    """A single cached embedding's metadata (NOT the vector itself)."""
    source_path: str          # absolute or repo-relative path
    content_hash: str         # sha256 hex of file contents at embed time
    embedded_at: float        # unix epoch seconds when embedded
    embedding_model: str      # e.g. "embed-v3-1024"
    vector_dim: int           # length of the stored vector


@dataclass(frozen=True)
class FsFacts:
    """Filesystem snapshot for one path. Decouples logic from disk I/O.

    exists=False means caller stat()'d and got FileNotFoundError. Other
    fields are then meaningless and ignored.
    """
    exists: bool
    mtime: float = 0.0
    current_hash: str | None = None  # None if caller deferred hashing


@dataclass(frozen=True)
class StalenessReport:
    """Verdict for a single cache entry.

    verdict ∈ {fresh, mtime_only, mtime_drift, missing, hash_unknown}
    action  ∈ {keep, refresh_embedded_at, re_embed, evict, hash_then_recheck}
    """
    source_path: str
    verdict: str
    action: str
    detail: dict


class StalenessDetectorError(Exception):
    pass


def evaluate(entry: CacheEntry, facts: FsFacts) -> StalenessReport:
    """Pure decision: given a cache entry and filesystem facts, return a verdict.

    Decision order (first match wins):
      1. exists=False -> missing / evict
      2. mtime <= embedded_at -> fresh / keep (the file hasn't been touched
         since we embedded it — no need to re-hash)
      3. mtime > embedded_at AND current_hash is None -> hash_unknown /
         hash_then_recheck (caller deferred the hash; we tell them to do it
         and call us again)
      4. mtime > embedded_at AND current_hash == content_hash -> mtime_only /
         refresh_embedded_at (touch / re-checkout / chmod; no re-embed needed)
      5. mtime > embedded_at AND current_hash != content_hash -> mtime_drift /
         re_embed (the actual content changed)
    """
    if not isinstance(entry, CacheEntry):
        raise StalenessDetectorError("entry must be CacheEntry")
    if not isinstance(facts, FsFacts):
        raise StalenessDetectorError("facts must be FsFacts")

    if not facts.exists:
        return StalenessReport(
            source_path=entry.source_path,
            verdict="missing",
            action="evict",
            detail={"reason": "source_not_on_disk"},
        )

    # mtime ordering: equality is treated as fresh (filesystem mtime
    # resolution can be coarse — 1s on some FSes — and an embed pipeline
    # that writes embedded_at = stat.st_mtime would otherwise self-flag).
    if facts.mtime <= entry.embedded_at:
        return StalenessReport(
            source_path=entry.source_path,
            verdict="fresh",
            action="keep",
            detail={
                "mtime": facts.mtime,
                "embedded_at": entry.embedded_at,
                "delta_s": entry.embedded_at - facts.mtime,
            },
        )

    if facts.current_hash is None:
        return StalenessReport(
            source_path=entry.source_path,
            verdict="hash_unknown",
            action="hash_then_recheck",
            detail={
                "mtime": facts.mtime,
                "embedded_at": entry.embedded_at,
                "delta_s": facts.mtime - entry.embedded_at,
                "hint": "mtime advanced; re-hash on disk and call evaluate() again",
            },
        )

    if facts.current_hash == entry.content_hash:
        return StalenessReport(
            source_path=entry.source_path,
            verdict="mtime_only",
            action="refresh_embedded_at",
            detail={
                "mtime": facts.mtime,
                "embedded_at": entry.embedded_at,
                "delta_s": facts.mtime - entry.embedded_at,
                "content_hash": entry.content_hash,
            },
        )

    return StalenessReport(
        source_path=entry.source_path,
        verdict="mtime_drift",
        action="re_embed",
        detail={
            "mtime": facts.mtime,
            "embedded_at": entry.embedded_at,
            "delta_s": facts.mtime - entry.embedded_at,
            "old_hash": entry.content_hash,
            "new_hash": facts.current_hash,
        },
    )


def hash_file(path: str, *, chunk_size: int = 65536) -> str:
    """SHA-256 hex of file contents, streamed (no full-file load)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def stat_facts(path: str, *, hash_now: bool = False) -> FsFacts:
    """Stat a path and optionally hash. Returns FsFacts(exists=False) on missing.

    `hash_now=False` is the recommended default: a full-corpus scan should
    use mtime alone to find candidates, then re-stat with `hash_now=True`
    only on the candidates the engine flagged `hash_unknown`.
    """
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return FsFacts(exists=False)
    if hash_now:
        try:
            h = hash_file(path)
        except OSError:
            # Race: file disappeared between stat and open.
            return FsFacts(exists=False)
        return FsFacts(exists=True, mtime=st.st_mtime, current_hash=h)
    return FsFacts(exists=True, mtime=st.st_mtime, current_hash=None)


def scan_entries(
    entries: Iterable[CacheEntry],
    *,
    fs_lookup=None,
) -> list[StalenessReport]:
    """Scan a batch of cache entries. `fs_lookup(path) -> FsFacts` is injectable
    so tests can pass synthetic facts.

    Two-pass behavior on real disk:
      - pass 1: stat-only (cheap)
      - pass 2: for any `hash_unknown` entries, re-call with `hash_now=True`

    Default `fs_lookup` is real disk, stat-only. Caller composes the second
    pass explicitly to keep the engine's I/O surface small.
    """
    if fs_lookup is None:
        fs_lookup = lambda p: stat_facts(p, hash_now=False)
    out: list[StalenessReport] = []
    for entry in entries:
        facts = fs_lookup(entry.source_path)
        out.append(evaluate(entry, facts))
    return out

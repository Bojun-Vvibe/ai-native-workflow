"""Worked example: embedding-staleness-detector-by-mtime.

Builds a small synthetic corpus on disk in a temp dir, embeds (faked) some
files, mutates them in five ways, runs the detector, and prints the verdict
table.

Five scenarios to cover the verdict surface:

  1. fresh:       file untouched since embed -> keep
  2. mtime_only:  file touched (mtime advanced) but content hash unchanged
                  -> refresh_embedded_at (no API call needed)
  3. mtime_drift: file content changed -> re_embed
  4. missing:     source file deleted -> evict
  5. hash_unknown -> after pass 2 hash, resolves to mtime_drift

Plus a deterministic-fixture pass that doesn't touch disk so the engine
itself is exercised against synthetic FsFacts.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from detector import (
    CacheEntry,
    FsFacts,
    StalenessReport,
    evaluate,
    hash_file,
    scan_entries,
    stat_facts,
)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _show(report: StalenessReport) -> None:
    print(f"  path:    {report.source_path}")
    print(f"  verdict: {report.verdict}")
    print(f"  action:  {report.action}")
    keys = sorted(report.detail.keys())
    for k in keys:
        v = report.detail[k]
        if isinstance(v, float):
            v = f"{v:.3f}"
        print(f"  {k}: {v}")
    print()


def main() -> None:
    print("=" * 60)
    print("PART A: synthetic FsFacts (no disk) — engine surface check")
    print("=" * 60)

    fixtures = [
        # 1. fresh: mtime <= embedded_at
        (
            CacheEntry("a.txt", "h_a", embedded_at=1000.0, embedding_model="m1", vector_dim=8),
            FsFacts(exists=True, mtime=999.0, current_hash="h_a"),
            "fresh",
        ),
        # 2. fresh on tie (mtime == embedded_at)
        (
            CacheEntry("a-tie.txt", "h_a", embedded_at=1000.0, embedding_model="m1", vector_dim=8),
            FsFacts(exists=True, mtime=1000.0, current_hash="h_a"),
            "fresh",
        ),
        # 3. mtime_only: mtime advanced, hash matches
        (
            CacheEntry("b.txt", "h_b", embedded_at=1000.0, embedding_model="m1", vector_dim=8),
            FsFacts(exists=True, mtime=1500.0, current_hash="h_b"),
            "mtime_only",
        ),
        # 4. mtime_drift: mtime advanced, hash differs
        (
            CacheEntry("c.txt", "h_c", embedded_at=1000.0, embedding_model="m1", vector_dim=8),
            FsFacts(exists=True, mtime=1500.0, current_hash="h_c_NEW"),
            "mtime_drift",
        ),
        # 5. missing
        (
            CacheEntry("d.txt", "h_d", embedded_at=1000.0, embedding_model="m1", vector_dim=8),
            FsFacts(exists=False),
            "missing",
        ),
        # 6. hash_unknown (caller deferred hashing)
        (
            CacheEntry("e.txt", "h_e", embedded_at=1000.0, embedding_model="m1", vector_dim=8),
            FsFacts(exists=True, mtime=1500.0, current_hash=None),
            "hash_unknown",
        ),
    ]

    for entry, facts, expected in fixtures:
        report = evaluate(entry, facts)
        print(f"--- expected {expected!r} ---")
        _show(report)
        assert report.verdict == expected, f"got {report.verdict!r}"

    # Action map invariant: every verdict produces exactly one stable action.
    expected_action = {
        "fresh": "keep",
        "mtime_only": "refresh_embedded_at",
        "mtime_drift": "re_embed",
        "missing": "evict",
        "hash_unknown": "hash_then_recheck",
    }
    for entry, facts, expected in fixtures:
        report = evaluate(entry, facts)
        assert report.action == expected_action[report.verdict], (
            f"verdict/action mismatch: {report.verdict} -> {report.action}"
        )
    print("invariant: every verdict maps to exactly one action (passes)")

    print()
    print("=" * 60)
    print("PART B: real disk — five-file corpus, scanned twice")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as td:
        # Build five files with known contents.
        names = ["fresh.txt", "touched.txt", "edited.txt", "deleted.txt", "deferred.txt"]
        paths = {n: os.path.join(td, n) for n in names}
        for n, p in paths.items():
            content = f"original content for {n}\n".encode()
            with open(p, "wb") as f:
                f.write(content)

        # Pretend we embedded all five at t0. Capture mtimes BEFORE mutation.
        t0 = time.time()
        entries = []
        for n, p in paths.items():
            with open(p, "rb") as f:
                data = f.read()
            entries.append(
                CacheEntry(
                    source_path=p,
                    content_hash=_sha256_bytes(data),
                    embedded_at=t0,
                    embedding_model="embed-v3-1024",
                    vector_dim=1024,
                )
            )

        # Sleep enough that any subsequent mtime advances are observable
        # even on coarse (1s-resolution) filesystems.
        time.sleep(1.1)

        # 1. fresh.txt: leave it alone.
        # 2. touched.txt: re-write the same content (mtime advances, hash same).
        with open(paths["touched.txt"], "wb") as f:
            f.write(b"original content for touched.txt\n")
        # 3. edited.txt: write different content.
        with open(paths["edited.txt"], "wb") as f:
            f.write(b"this content is now different\n")
        # 4. deleted.txt: remove it.
        os.remove(paths["deleted.txt"])
        # 5. deferred.txt: write different content but we will pass current_hash=None
        #    on pass 1 (no hash), then pass 2 with the real hash.
        with open(paths["deferred.txt"], "wb") as f:
            f.write(b"different content for deferred\n")

        # Pass 1: stat-only.
        print("--- Pass 1: stat-only (no file reads) ---")
        pass1 = scan_entries(entries)  # default fs_lookup is stat-only
        for r in pass1:
            print(f"{os.path.basename(r.source_path):20s} -> {r.verdict:13s} action={r.action}")

        # Quick sanity: every pass-1 verdict for non-deleted files that mtime-advanced
        # should be `hash_unknown` (because current_hash=None).
        for r in pass1:
            base = os.path.basename(r.source_path)
            if base == "fresh.txt":
                assert r.verdict == "fresh"
            elif base == "deleted.txt":
                assert r.verdict == "missing"
            else:
                assert r.verdict == "hash_unknown", f"{base}: {r.verdict}"

        # Pass 2: re-scan only the hash_unknown candidates with a real hash.
        print()
        print("--- Pass 2: re-hash candidates flagged hash_unknown ---")
        candidates = [r for r in pass1 if r.verdict == "hash_unknown"]
        # Build a per-path entry index to retrieve the original entry quickly.
        entry_by_path = {e.source_path: e for e in entries}
        pass2: list[StalenessReport] = []
        for r in candidates:
            entry = entry_by_path[r.source_path]
            facts = stat_facts(r.source_path, hash_now=True)
            pass2.append(evaluate(entry, facts))
        for r in pass2:
            print(f"{os.path.basename(r.source_path):20s} -> {r.verdict:13s} action={r.action}")

        # Final verdict summary.
        print()
        print("--- Final verdict per file (pass2 wins where present) ---")
        merged: dict[str, StalenessReport] = {}
        for r in pass1:
            merged[r.source_path] = r
        for r in pass2:
            merged[r.source_path] = r
        # Stable order by basename.
        for path in sorted(merged.keys(), key=os.path.basename):
            r = merged[path]
            print(f"{os.path.basename(r.source_path):20s} verdict={r.verdict:13s} action={r.action}")

        # Verify each file ended in the expected verdict.
        expected_final = {
            "fresh.txt": "fresh",
            "touched.txt": "mtime_only",
            "edited.txt": "mtime_drift",
            "deleted.txt": "missing",
            "deferred.txt": "mtime_drift",
        }
        print()
        for path, r in merged.items():
            base = os.path.basename(path)
            assert r.verdict == expected_final[base], (
                f"{base}: expected {expected_final[base]!r}, got {r.verdict!r}"
            )
        print("invariant: every file landed in its expected verdict (passes)")


if __name__ == "__main__":
    main()

"""Worked example for ``embedding-dimension-mismatch-guard``.

Six scenarios covering all five verdicts plus the bulk-write per-vector
sweep, plus a config-time error.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guard import (
    ModelSpec,
    IndexSpec,
    GuardConfigError,
    check_query,
    check_upsert,
)


def line(r) -> str:
    return (
        f"   verdict={r.verdict}\n"
        f"   reason: {r.reason}\n"
        f"   fingerprints: expected={r.expected_fingerprint} actual={r.actual_fingerprint}"
    )


def run() -> None:
    # The index was built three weeks ago against embedder-v2 / 1536 / cosine / normalized.
    index = IndexSpec(
        index_id="docs-prod-v2",
        expected_model_id="embedder-v2",
        dim=1536,
        metric="cosine",
        normalize=True,
    )

    print("1. ok: matching model")
    m_ok = ModelSpec("embedder-v2", 1536, "cosine", True)
    r = check_query(m_ok, index)
    print(line(r) + "\n")

    print("2. model_id_mismatch: someone swapped to embedder-v3 silently")
    m_idmismatch = ModelSpec("embedder-v3", 1536, "cosine", True)
    r = check_query(m_idmismatch, index)
    print(line(r) + "\n")

    print("3. dim_mismatch: same model name, but a 'large' variant returns 3072 dims")
    m_dim = ModelSpec("embedder-v2", 3072, "cosine", True)
    r = check_query(m_dim, index)
    print(line(r) + "\n")

    print("4. metric_mismatch: dims match but the index was cosine, query is dot")
    m_metric = ModelSpec("embedder-v2", 1536, "dot", True)
    r = check_query(m_metric, index)
    print(line(r) + "\n")

    print("5. normalization_mismatch: index normalized, model returns un-normalized")
    m_norm = ModelSpec("embedder-v2", 1536, "cosine", False)
    r = check_query(m_norm, index)
    print(line(r) + "\n")

    print("6. upsert: contract ok, but two of five vectors have wrong dim")
    vectors = [
        [0.1] * 1536,   # ok
        [0.1] * 1536,   # ok
        [0.1] * 1535,   # short — partial response from upstream
        [0.1] * 1536,   # ok
        [0.1] * 768,    # very wrong — different model code path
    ]
    r = check_upsert(m_ok, index, vectors)
    print(line(r))
    print(f"   rejected indices: {r.rejected_vector_indices}\n")

    # Config-time errors.
    print("7. construction errors are loud (not silent defaults)")
    try:
        ModelSpec("embedder-v2", 0, "cosine", True)
    except GuardConfigError as e:
        print(f"   ModelSpec(dim=0) raised: {e}")
    try:
        IndexSpec("docs", "embedder-v2", 1536, "manhattan", True)
    except GuardConfigError as e:
        print(f"   IndexSpec(metric='manhattan') raised: {e}")

    # Runtime invariants.
    fp_a = ModelSpec("embedder-v2", 1536, "cosine", True).content_fingerprint
    fp_b = ModelSpec("embedder-v2", 1536, "cosine", True).content_fingerprint
    fp_c = ModelSpec("embedder-v2", 1536, "cosine", False).content_fingerprint
    assert fp_a == fp_b, "fingerprint must be deterministic"
    assert fp_a != fp_c, "fingerprint must include normalize"
    print("\ninvariants ok: fingerprint deterministic; normalize-flip changes fingerprint")


if __name__ == "__main__":
    run()

"""Pre-flight guard against vector / index dimension mismatches.

The single most common silent failure in a retrieval-augmented system is
"the index was built with model A (dim=1536), the query is being embedded
with model B (dim=3072 or dim=768)". The vector store either refuses the
query at the worst possible moment, or — much worse — silently truncates
or zero-pads it and returns junk neighbors that *look* plausible.

This guard catches the mismatch *before* the query embedding is computed
or sent. It also catches the bulk-write variant (an index built against
one model spec being asked to ``upsert`` vectors from a different model).

Hard rules
----------
- Pure stdlib (``dataclasses``, ``hashlib``).
- No I/O, no network — caller hands in an ``IndexSpec`` and a
  ``ModelSpec`` (both small frozen records).
- Verdict is one of ``ok``, ``dim_mismatch``, ``model_id_mismatch``,
  ``metric_mismatch``, ``normalization_mismatch``. Each maps to a
  different recovery path; "the dims happen to match by coincidence" is
  *not* ``ok``, because cosine vs L2 still ruins recall.
- A pinned-in-code ``content_fingerprint`` (sha256 of model_id + dim +
  metric + normalize) lets the orchestrator stamp every embedding it
  writes; on read, mismatch surfaces immediately rather than at recall
  evaluation time three weeks later.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, List


class GuardConfigError(ValueError):
    """Raised at construction for impossible specs (dim<=0, unknown metric)."""


_ALLOWED_METRICS = ("cosine", "dot", "l2")


@dataclass(frozen=True)
class ModelSpec:
    """How a particular embedding model produces vectors.

    ``normalize`` is the model's *contract*, not a hint — if the model
    returns L2-normalized vectors and the index was built assuming
    un-normalized + cosine, recall will be silently degraded.
    """
    model_id: str
    dim: int
    metric: str           # cosine | dot | l2
    normalize: bool

    def __post_init__(self) -> None:
        if self.dim <= 0:
            raise GuardConfigError(f"dim must be > 0, got {self.dim}")
        if self.metric not in _ALLOWED_METRICS:
            raise GuardConfigError(
                f"metric must be one of {_ALLOWED_METRICS}, got {self.metric!r}"
            )
        if not self.model_id:
            raise GuardConfigError("model_id must be a non-empty string")

    @property
    def content_fingerprint(self) -> str:
        """Deterministic 12-hex-char id for stamping written vectors."""
        h = hashlib.sha256()
        h.update(self.model_id.encode("utf-8"))
        h.update(b"\x00")
        h.update(str(self.dim).encode("ascii"))
        h.update(b"\x00")
        h.update(self.metric.encode("ascii"))
        h.update(b"\x00")
        h.update(b"1" if self.normalize else b"0")
        return h.hexdigest()[:12]


@dataclass(frozen=True)
class IndexSpec:
    """What an existing vector index was built to accept.

    Mirror of ``ModelSpec``. Pinned at index-create time and read back
    from the index's metadata on every guard call (NOT inferred from the
    first vector's length — that is exactly the silent-failure path the
    guard exists to prevent).
    """
    index_id: str
    expected_model_id: str
    dim: int
    metric: str
    normalize: bool

    def __post_init__(self) -> None:
        if self.dim <= 0:
            raise GuardConfigError(f"dim must be > 0, got {self.dim}")
        if self.metric not in _ALLOWED_METRICS:
            raise GuardConfigError(
                f"metric must be one of {_ALLOWED_METRICS}, got {self.metric!r}"
            )
        if not self.index_id:
            raise GuardConfigError("index_id must be a non-empty string")
        if not self.expected_model_id:
            raise GuardConfigError("expected_model_id must be a non-empty string")


@dataclass
class GuardResult:
    verdict: str           # ok | dim_mismatch | model_id_mismatch | metric_mismatch | normalization_mismatch
    reason: str
    index_id: str
    model_id: str
    expected_dim: int
    actual_dim: int
    expected_fingerprint: str
    actual_fingerprint: str
    rejected_vector_indices: List[int] = field(default_factory=list)


def check_query(model: ModelSpec, index: IndexSpec) -> GuardResult:
    """Pre-flight check before computing or sending a query embedding.

    Order of checks is deliberate: ``model_id`` first (the most diagnostic
    signal — if the names don't match, the rest of the diff is noise),
    then ``dim`` (the failure mode that silently truncates), then
    ``metric``, then ``normalize``. First-mismatch-wins so the reason
    string points at the *root cause*, not the cascade.
    """
    expected_fp = _expected_fp_from_index(index)
    actual_fp = model.content_fingerprint

    if model.model_id != index.expected_model_id:
        return GuardResult(
            verdict="model_id_mismatch",
            reason=(
                f"index {index.index_id!r} expects model "
                f"{index.expected_model_id!r}, got {model.model_id!r}"
            ),
            index_id=index.index_id,
            model_id=model.model_id,
            expected_dim=index.dim,
            actual_dim=model.dim,
            expected_fingerprint=expected_fp,
            actual_fingerprint=actual_fp,
        )
    if model.dim != index.dim:
        return GuardResult(
            verdict="dim_mismatch",
            reason=(
                f"index {index.index_id!r} dim={index.dim}, model "
                f"{model.model_id!r} dim={model.dim}"
            ),
            index_id=index.index_id,
            model_id=model.model_id,
            expected_dim=index.dim,
            actual_dim=model.dim,
            expected_fingerprint=expected_fp,
            actual_fingerprint=actual_fp,
        )
    if model.metric != index.metric:
        return GuardResult(
            verdict="metric_mismatch",
            reason=(
                f"index metric={index.metric}, model metric={model.metric} "
                "(dims match but recall will be silently degraded)"
            ),
            index_id=index.index_id,
            model_id=model.model_id,
            expected_dim=index.dim,
            actual_dim=model.dim,
            expected_fingerprint=expected_fp,
            actual_fingerprint=actual_fp,
        )
    if model.normalize != index.normalize:
        return GuardResult(
            verdict="normalization_mismatch",
            reason=(
                f"index normalize={index.normalize}, model normalize="
                f"{model.normalize} (cosine math assumes one or the other; "
                "mixing silently shifts the score distribution)"
            ),
            index_id=index.index_id,
            model_id=model.model_id,
            expected_dim=index.dim,
            actual_dim=model.dim,
            expected_fingerprint=expected_fp,
            actual_fingerprint=actual_fp,
        )
    return GuardResult(
        verdict="ok",
        reason=f"all four contract fields match (fp={actual_fp})",
        index_id=index.index_id,
        model_id=model.model_id,
        expected_dim=index.dim,
        actual_dim=model.dim,
        expected_fingerprint=expected_fp,
        actual_fingerprint=actual_fp,
    )


def check_upsert(
    model: ModelSpec,
    index: IndexSpec,
    vectors: Iterable[Iterable[float]],
) -> GuardResult:
    """Bulk-write check: same contract as ``check_query`` plus a
    per-vector dim sanity sweep.

    Even when the contract matches at the spec level, an individual
    upserted vector with the wrong length is the second-most-common
    silent corruption (truncated embedding from a partial response, or
    a different code path that bypassed the model wrapper). Reject the
    *whole* batch if any vector mismatches, and report the offending
    indices so the caller can re-embed them surgically.
    """
    pre = check_query(model, index)
    if pre.verdict != "ok":
        return pre
    bad: List[int] = []
    for i, v in enumerate(vectors):
        # ``v`` may be any iterable of floats; consume into a list to get a length.
        vec = list(v)
        if len(vec) != index.dim:
            bad.append(i)
    if bad:
        return GuardResult(
            verdict="dim_mismatch",
            reason=(
                f"{len(bad)} vector(s) of wrong dim in batch (expected "
                f"{index.dim}); indices: {bad[:10]}"
                + (" ..." if len(bad) > 10 else "")
            ),
            index_id=index.index_id,
            model_id=model.model_id,
            expected_dim=index.dim,
            actual_dim=-1,
            expected_fingerprint=pre.expected_fingerprint,
            actual_fingerprint=pre.actual_fingerprint,
            rejected_vector_indices=bad,
        )
    return pre  # ok


def _expected_fp_from_index(index: IndexSpec) -> str:
    """Compute the fingerprint an *expected* model would produce.

    Reconstructed from the index spec so the orchestrator can compare
    `actual` (from the model) and `expected` (from the index) without
    needing to keep an extra `ModelSpec` floating around at the index
    boundary.
    """
    h = hashlib.sha256()
    h.update(index.expected_model_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(index.dim).encode("ascii"))
    h.update(b"\x00")
    h.update(index.metric.encode("ascii"))
    h.update(b"\x00")
    h.update(b"1" if index.normalize else b"0")
    return h.hexdigest()[:12]

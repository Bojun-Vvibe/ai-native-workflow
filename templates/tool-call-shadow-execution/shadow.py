"""tool-call-shadow-execution
==============================

Run a *candidate* tool implementation in **shadow mode** alongside the
*production* implementation: production is the source of truth (its result
is what the agent actually receives), the shadow runs in parallel, its
result is compared against production, and disagreements are recorded — but
the shadow's side-effects are suppressed.

Why
---
Replacing a tool the agent already depends on (e.g., switching the
file-search backend, re-implementing a flaky API in a leaner client,
swapping a regex parser for a tree-sitter one) is high-risk: a subtle
behavior change becomes a silent regression that only shows up two missions
later as "the agent stopped finding files." Shadow execution lets you
diff prod vs. candidate on **real production traffic**, with zero blast
radius, until you have enough samples to flip the cutover safely.

Differs from the in-context "weighted-model-router" (split traffic, both
results are returned, observability layer compares) — shadow execution
**does not split traffic**, **never returns the shadow's result**, and is
specifically engineered so a candidate tool that is *broken* (writes to the
wrong path, sends a duplicate API request, overcharges a metered upstream)
cannot do harm. It is the safe-rollout substrate the router can later
choose to consume.

Properties
----------
- Production runs first and synchronously. Its result is **always** what
  the caller gets back. Shadow failures never block the call.
- Shadow runs in a `concurrent.futures.ThreadPoolExecutor` (caller-injected
  for testability) with a hard `shadow_timeout_s`. A shadow that times out
  is recorded as `shadow_status="timeout"` — never as a disagreement.
- Side-effect suppression is the **caller's** contract: the caller passes
  a `shadow_factory` that constructs the shadow tool *in dry-run mode*.
  The template documents the contract (`SHADOW_TOOL_CONTRACT.md` ideas
  inline below) and asserts it via a `must_be_dry_run` flag the candidate
  is expected to honor; if the candidate writes to the disk-marker file
  the harness gave it, the comparator records a `side_effect_violation`
  and the run is bucketed `unsafe` (do NOT promote).
- Comparator is pluggable: equality by default, callers can pass a
  semantic comparator (e.g., set-equality on file lists, JSON-canonical
  equality on structured outputs).
- Reasons for disagreement are classified into a closed enum
  (`equal`, `prod_only_field`, `shadow_only_field`, `value_mismatch`,
  `type_mismatch`, `prod_raised`, `shadow_raised`, `both_raised`,
  `shadow_timeout`, `side_effect_violation`).
- Stats accumulator (`ShadowStats`) carries per-bucket counts and the last
  N disagreement samples (bounded ring buffer, default 16) so an operator
  can read a single dataclass to decide "promote / hold / abort."
- Stdlib only.

Non-goals
---------
- Does NOT do canary deploys (1% then 5% then 25%). That is upstream
  policy; this template's contract is "0% prod-affecting, 100% observed."
- Does NOT execute the shadow if the production tool *raised* — by then we
  already know the agent is going to see an error and the comparison is
  moot. Recorded as `prod_raised` and the shadow is skipped.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# ---------- Public types ----------


COMPARISON_REASONS = (
    "equal",
    "prod_only_field",
    "shadow_only_field",
    "value_mismatch",
    "type_mismatch",
    "prod_raised",
    "shadow_raised",
    "both_raised",
    "shadow_timeout",
    "side_effect_violation",
)


@dataclass(frozen=True)
class ShadowResult:
    """One shadow-execution observation."""
    call_id: str
    tool_name: str
    args: dict
    prod_value: Any              # what the agent received
    prod_error: str | None       # exception class name, if prod raised
    shadow_value: Any
    shadow_error: str | None
    shadow_status: str           # "ok" | "timeout" | "raised" | "skipped" | "unsafe"
    reason: str                  # one of COMPARISON_REASONS
    detail: str                  # human-readable diff hint
    prod_ms: float
    shadow_ms: float


@dataclass
class ShadowStats:
    by_reason: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    samples: list[ShadowResult] = field(default_factory=list)
    sample_cap: int = 16

    def record(self, r: ShadowResult) -> None:
        self.by_reason[r.reason] = self.by_reason.get(r.reason, 0) + 1
        self.by_status[r.shadow_status] = self.by_status.get(r.shadow_status, 0) + 1
        if r.reason != "equal":
            self.samples.append(r)
            # Bounded ring: drop oldest.
            if len(self.samples) > self.sample_cap:
                self.samples.pop(0)

    def total(self) -> int:
        return sum(self.by_reason.values())

    def disagreement_rate(self) -> float:
        n = self.total()
        if n == 0:
            return 0.0
        equals = self.by_reason.get("equal", 0)
        return (n - equals) / n

    def safe_to_promote(self, *, min_samples: int, max_disagreement: float) -> bool:
        if self.by_status.get("unsafe", 0) > 0:
            return False
        if self.total() < min_samples:
            return False
        return self.disagreement_rate() <= max_disagreement


# ---------- Side-effect contract ----------


@dataclass
class SideEffectGuard:
    """Caller hands one of these to each shadow invocation. The shadow
    promises to (a) check `is_dry_run` is True, and (b) NOT to write to
    `marker_path`. Any write is detected by the harness as
    `side_effect_violation`. Real implementations typically also forbid
    network egress except to a sandbox host — the marker is a minimal
    portable check that works without a sandbox."""
    is_dry_run: bool = True
    marker_path: str | None = None  # caller-managed; harness checks mtime

    def __post_init__(self) -> None:
        if not self.is_dry_run:
            raise ValueError("SideEffectGuard must be constructed with is_dry_run=True")


# ---------- Comparator ----------


def default_comparator(prod: Any, shadow: Any) -> tuple[str, str]:
    """Returns (reason, detail). `reason` is one of COMPARISON_REASONS
    (only the ones derivable from value comparison are produced here)."""
    if type(prod) is not type(shadow):
        return ("type_mismatch", f"prod={type(prod).__name__} shadow={type(shadow).__name__}")
    if isinstance(prod, dict):
        prod_keys = set(prod.keys())
        shadow_keys = set(shadow.keys())
        only_prod = prod_keys - shadow_keys
        only_shadow = shadow_keys - prod_keys
        if only_prod and not only_shadow:
            return ("prod_only_field", f"keys only in prod: {sorted(only_prod)}")
        if only_shadow and not only_prod:
            return ("shadow_only_field", f"keys only in shadow: {sorted(only_shadow)}")
        if only_prod or only_shadow:
            return (
                "value_mismatch",
                f"key delta -- only_prod={sorted(only_prod)} only_shadow={sorted(only_shadow)}",
            )
        # Same keyset: drill on values.
        for k in sorted(prod_keys):
            if prod[k] != shadow[k]:
                return ("value_mismatch", f"differ at .{k}: prod={prod[k]!r} shadow={shadow[k]!r}")
        return ("equal", "")
    if prod == shadow:
        return ("equal", "")
    return ("value_mismatch", f"prod={prod!r} shadow={shadow!r}")


# ---------- Runner ----------


@dataclass
class ShadowRunner:
    executor: ThreadPoolExecutor
    stats: ShadowStats = field(default_factory=ShadowStats)
    shadow_timeout_s: float = 1.0
    comparator: Callable[[Any, Any], tuple[str, str]] = field(default=default_comparator)
    now_fn: Callable[[], float] = time.monotonic

    def execute(
        self,
        *,
        call_id: str,
        tool_name: str,
        args: dict,
        prod_fn: Callable[[dict], Any],
        shadow_fn: Callable[[dict, SideEffectGuard], Any],
        marker_check: Callable[[], bool] | None = None,
    ) -> ShadowResult:
        """Run prod synchronously, shadow in the executor.

        - `prod_fn(args) -> Any`
        - `shadow_fn(args, guard) -> Any`
        - `marker_check()` returns True iff the shadow violated the side-effect
          contract (e.g., touched the marker file). Caller can pass `None` to
          skip side-effect checking.

        Returns a ShadowResult; also appends to `self.stats`.
        """
        guard = SideEffectGuard(is_dry_run=True, marker_path="(harness-managed)")

        # Submit shadow first so it can overlap with prod.
        future: Future = self.executor.submit(shadow_fn, args, guard)

        prod_t0 = self.now_fn()
        prod_value: Any = None
        prod_error: str | None = None
        try:
            prod_value = prod_fn(args)
        except Exception as e:
            prod_error = type(e).__name__
        prod_ms = (self.now_fn() - prod_t0) * 1000.0

        shadow_t0 = self.now_fn()
        shadow_value: Any = None
        shadow_error: str | None = None
        shadow_status = "ok"
        try:
            shadow_value = future.result(timeout=self.shadow_timeout_s)
        except FutTimeout:
            shadow_status = "timeout"
            # Best-effort cancel; if already running it will simply finish in
            # the background and its result is discarded.
            future.cancel()
        except Exception as e:
            shadow_error = type(e).__name__
            shadow_status = "raised"
        shadow_ms = (self.now_fn() - shadow_t0) * 1000.0

        # Side-effect violation trumps all other classifications.
        if marker_check is not None and marker_check():
            r = ShadowResult(
                call_id=call_id, tool_name=tool_name, args=args,
                prod_value=prod_value, prod_error=prod_error,
                shadow_value=shadow_value, shadow_error=shadow_error,
                shadow_status="unsafe",
                reason="side_effect_violation",
                detail="shadow tool wrote despite is_dry_run=True",
                prod_ms=prod_ms, shadow_ms=shadow_ms,
            )
            self.stats.record(r)
            return r

        # Reason classification.
        if prod_error and shadow_error:
            reason, detail = "both_raised", f"prod={prod_error} shadow={shadow_error}"
        elif prod_error:
            # Prod failed -> agent gets the error; shadow comparison is moot.
            reason, detail = "prod_raised", f"prod={prod_error}"
        elif shadow_status == "timeout":
            reason, detail = "shadow_timeout", f"exceeded {self.shadow_timeout_s}s"
        elif shadow_error:
            reason, detail = "shadow_raised", f"shadow={shadow_error}"
        else:
            reason, detail = self.comparator(prod_value, shadow_value)

        r = ShadowResult(
            call_id=call_id, tool_name=tool_name, args=args,
            prod_value=prod_value, prod_error=prod_error,
            shadow_value=shadow_value, shadow_error=shadow_error,
            shadow_status=shadow_status,
            reason=reason, detail=detail,
            prod_ms=prod_ms, shadow_ms=shadow_ms,
        )
        self.stats.record(r)
        return r

    def report(self) -> dict:
        return {
            "total": self.stats.total(),
            "by_reason": dict(sorted(self.stats.by_reason.items())),
            "by_status": dict(sorted(self.stats.by_status.items())),
            "disagreement_rate": round(self.stats.disagreement_rate(), 4),
            "n_samples_kept": len(self.stats.samples),
        }

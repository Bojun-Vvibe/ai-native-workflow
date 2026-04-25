"""agent-tool-call-retry-backoff-fairness-checker

Pure stdlib detector that audits an agent's retry timing log to
confirm the retries actually backed off, instead of degenerating
into a tight loop that hammers a flaky downstream until budget runs
out.

The contract: when an agent retries the same logical tool call after
a transient failure, successive delays should *grow* (typically by
a multiplicative factor like 2x) up to a ceiling. The checker fires
when:

- delays are flat or shrinking when they should grow,
- the multiplicative ratio between consecutive delays is far below
  the configured target (e.g. agent claims "exponential 2x" but the
  observed ratio is 1.05),
- the first delay is below a configured floor (a hot retry — the
  retry happened almost immediately after the failure),
- the same `(tool, fingerprint)` was retried more than the
  configured `max_attempts`,
- jitter is *too low*: every delay differs from its neighbour by
  less than `jitter_floor_ms` — a sign the agent is scheduling
  retries in lockstep across replicas (thundering-herd risk).

This is a *fairness* check, not a correctness check. It does not
care whether the retries eventually succeeded; it cares whether the
retry policy was honest.

Stdlib only. Pure function over an in-memory list of attempts.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple


class BackoffValidationError(ValueError):
    """Raised eagerly on malformed input."""


@dataclass(frozen=True)
class Finding:
    kind: str          # one of: hot_retry, flat_or_shrinking, ratio_below_target,
                       # too_many_attempts, jitter_floor_violation
    fingerprint: str   # tool + canonical args fingerprint
    detail: str


@dataclass
class FairnessReport:
    ok: bool
    per_fingerprint: Dict[str, Dict[str, float]] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "per_fingerprint": self.per_fingerprint,
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            sort_keys=True,
        )


def _canonicalize_args(args) -> str:
    """Stable string fingerprint of a JSON-able arg dict."""
    if args is None:
        return "null"
    return json.dumps(args, sort_keys=True, separators=(",", ":"))


def _validate_attempt(a) -> None:
    if not isinstance(a, dict):
        raise BackoffValidationError(f"attempt must be dict, got {type(a).__name__}")
    for k in ("tool", "args", "delay_before_ms", "outcome"):
        if k not in a:
            raise BackoffValidationError(f"attempt missing key: {k!r}")
    if not isinstance(a["tool"], str) or not a["tool"]:
        raise BackoffValidationError("attempt.tool must be non-empty str")
    d = a["delay_before_ms"]
    if not isinstance(d, (int, float)) or isinstance(d, bool) or d < 0:
        raise BackoffValidationError(
            f"attempt.delay_before_ms must be non-negative number, got {d!r}"
        )
    if a["outcome"] not in ("success", "failure"):
        raise BackoffValidationError(
            f"attempt.outcome must be 'success' or 'failure', got {a['outcome']!r}"
        )


def check(
    attempts: list,
    *,
    target_ratio: float = 2.0,
    ratio_tolerance: float = 0.5,
    initial_delay_floor_ms: int = 50,
    max_attempts: int = 5,
    jitter_floor_ms: int = 5,
) -> FairnessReport:
    """Audit retry-backoff fairness across a list of attempts.

    Args:
        attempts: ordered list of `{tool, args, delay_before_ms,
            outcome}` dicts. The very first attempt of a given
            `(tool, fingerprint)` should normally have
            `delay_before_ms == 0`; the first *retry* is the second
            attempt and is the one with a meaningful pre-delay.
        target_ratio: expected multiplicative growth between
            successive delays of the same fingerprint.
        ratio_tolerance: max acceptable absolute deviation from
            `target_ratio`. With `target_ratio=2.0` and
            `ratio_tolerance=0.5`, observed ratios in
            `[1.5, 2.5]` pass; outside that window fires
            `ratio_below_target`.
        initial_delay_floor_ms: minimum acceptable delay on the
            first retry (the *second* attempt). Below this, fires
            `hot_retry`.
        max_attempts: hard cap. More attempts on the same
            fingerprint fires `too_many_attempts`.
        jitter_floor_ms: minimum acceptable per-step variation
            between consecutive retries' delays. If every
            consecutive pair differs by less than this, fires
            `jitter_floor_violation` (lockstep risk).

    Returns:
        FairnessReport with `ok=False` iff any finding fires.
    """
    if not isinstance(attempts, list):
        raise BackoffValidationError(
            f"attempts must be list, got {type(attempts).__name__}"
        )
    for a in attempts:
        _validate_attempt(a)

    # group by (tool, fingerprint), preserving order
    groups: Dict[str, List[Tuple[int, dict]]] = {}
    order: List[str] = []
    for idx, a in enumerate(attempts):
        fp = f"{a['tool']}::{_canonicalize_args(a['args'])}"
        if fp not in groups:
            groups[fp] = []
            order.append(fp)
        groups[fp].append((idx, a))

    findings: List[Finding] = []
    per_fp: Dict[str, Dict[str, float]] = {}

    for fp in order:
        group = groups[fp]
        attempts_count = len(group)
        # delays for retries only — the first attempt's delay is the
        # initial scheduling delay (often 0) and not a retry decision.
        retry_delays = [a["delay_before_ms"] for _, a in group[1:]]

        per_fp[fp] = {
            "attempts": float(attempts_count),
            "retry_delays_ms": list(retry_delays),
        }

        # too_many_attempts
        if attempts_count > max_attempts:
            findings.append(
                Finding(
                    "too_many_attempts",
                    fp,
                    f"{attempts_count} attempts exceed max_attempts={max_attempts}",
                )
            )

        # hot_retry: first retry below floor
        if retry_delays and retry_delays[0] < initial_delay_floor_ms:
            findings.append(
                Finding(
                    "hot_retry",
                    fp,
                    f"first retry delay {retry_delays[0]}ms below floor {initial_delay_floor_ms}ms",
                )
            )

        # flat_or_shrinking + ratio_below_target
        for i in range(1, len(retry_delays)):
            prev, cur = retry_delays[i - 1], retry_delays[i]
            if prev <= 0:
                # cannot meaningfully compute ratio against zero;
                # report flat/shrinking only if cur also <= 0.
                if cur <= 0:
                    findings.append(
                        Finding(
                            "flat_or_shrinking",
                            fp,
                            f"retry delays {prev}ms -> {cur}ms (no growth)",
                        )
                    )
                continue
            if cur <= prev:
                findings.append(
                    Finding(
                        "flat_or_shrinking",
                        fp,
                        f"retry delays {prev}ms -> {cur}ms (no growth)",
                    )
                )
                continue
            ratio = cur / prev
            if abs(ratio - target_ratio) > ratio_tolerance:
                findings.append(
                    Finding(
                        "ratio_below_target",
                        fp,
                        f"retry ratio {ratio:.2f} outside [{target_ratio - ratio_tolerance:.2f}, {target_ratio + ratio_tolerance:.2f}]",
                    )
                )

        # jitter_floor_violation: every consecutive pair differs
        # by less than jitter_floor_ms (sign of lockstep scheduling)
        if len(retry_delays) >= 3:
            diffs = [
                abs(retry_delays[i] - retry_delays[i - 1])
                for i in range(1, len(retry_delays))
            ]
            if all(d < jitter_floor_ms for d in diffs):
                findings.append(
                    Finding(
                        "jitter_floor_violation",
                        fp,
                        f"all consecutive delay diffs {diffs} below jitter floor {jitter_floor_ms}ms",
                    )
                )

    findings.sort(key=lambda f: (f.kind, f.fingerprint, f.detail))
    return FairnessReport(ok=not findings, per_fingerprint=per_fp, findings=findings)


# ---------------------------------------------------------------------------
# Worked example
# ---------------------------------------------------------------------------

def _mk(tool, args, delay, outcome):
    return {"tool": tool, "args": args, "delay_before_ms": delay, "outcome": outcome}


_CASES = [
    (
        "01_clean_exponential",
        # honest 2x growth: 0, 100, 200, 400 — third retry succeeds
        [
            _mk("http_get", {"url": "/x"}, 0, "failure"),
            _mk("http_get", {"url": "/x"}, 100, "failure"),
            _mk("http_get", {"url": "/x"}, 200, "failure"),
            _mk("http_get", {"url": "/x"}, 400, "success"),
        ],
    ),
    (
        "02_hot_retry",
        # first retry only 5ms after failure — well below 50ms floor
        [
            _mk("http_get", {"url": "/y"}, 0, "failure"),
            _mk("http_get", {"url": "/y"}, 5, "failure"),
            _mk("http_get", {"url": "/y"}, 200, "success"),
        ],
    ),
    (
        "03_flat",
        # delays do not grow at all
        [
            _mk("query_db", {"q": "SELECT"}, 0, "failure"),
            _mk("query_db", {"q": "SELECT"}, 100, "failure"),
            _mk("query_db", {"q": "SELECT"}, 100, "failure"),
            _mk("query_db", {"q": "SELECT"}, 100, "failure"),
        ],
    ),
    (
        "04_too_many_attempts",
        # 7 attempts on the same call, max is 5
        [_mk("flaky", {}, 0 if i == 0 else 100 * (2 ** (i - 1)), "failure") for i in range(7)],
    ),
    (
        "05_ratio_off_target",
        # delays grow but only ~1.05x — agent claims 2x policy
        [
            _mk("rpc", {"m": "ping"}, 0, "failure"),
            _mk("rpc", {"m": "ping"}, 100, "failure"),
            _mk("rpc", {"m": "ping"}, 105, "failure"),
            _mk("rpc", {"m": "ping"}, 110, "failure"),
        ],
    ),
    (
        "06_lockstep_jitter",
        # delays grow but every diff is < 5ms — three replicas in lockstep
        [
            _mk("upload", {"f": "a"}, 0, "failure"),
            _mk("upload", {"f": "a"}, 100, "failure"),
            _mk("upload", {"f": "a"}, 102, "failure"),
            _mk("upload", {"f": "a"}, 103, "failure"),
        ],
    ),
]


def _run_demo() -> None:
    print("# agent-tool-call-retry-backoff-fairness-checker — worked example")
    print()
    for name, attempts in _CASES:
        print(f"## case {name}")
        print(f"attempts: {len(attempts)}")
        result = check(attempts)
        print(result.to_json())
        print()


if __name__ == "__main__":
    _run_demo()

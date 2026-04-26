#!/usr/bin/env python3
"""
agent-tool-call-output-size-distribution-checker
================================================

Stdlib-only auditor that reads a JSONL agent trace where each line
is a single tool call with at least:

    {"call_index": 0, "tool": "search", "output_bytes": 1234}

For each tool name independently, it computes a robust distribution
(median + MAD) of `output_bytes` across all calls, then flags
individual calls whose size is suspiciously off-distribution.

Six finding classes:

- ``empty_output``                — output_bytes == 0; almost
                                    always a silent error.
- ``size_outlier_high``           — > median + k*MAD (default k=6).
                                    Likely runaway result, OOM
                                    risk, or context blowup.
- ``size_outlier_low``            — < max(1, median - k*MAD) and
                                    median > 64. Likely truncation
                                    or partial failure.
- ``size_at_round_cap``           — output_bytes is within 1% of a
                                    common cap (1024, 2048, 4096,
                                    8192, 16384, 32768, 65536,
                                    131072). Strong signal the tool
                                    silently truncated.
- ``size_run_monotone_decay``     — three or more consecutive calls
                                    of the same tool where each
                                    output is strictly smaller than
                                    the previous AND the last one
                                    is < 50% of the first. Common
                                    when an upstream cache is
                                    cooling, a paginator is
                                    advancing past real data, or a
                                    quota is throttling.
- ``size_variance_collapse``      — the tool was called >= 5 times
                                    and ALL outputs are identical
                                    in size to the byte. Either the
                                    tool is returning a fixed-shape
                                    error envelope (think 404 JSON)
                                    or a stub is in the loop.

Findings are emitted in deterministic order: by tool name, then by
call_index, then by finding class.

Input: one JSONL path on argv[1].
Output: JSONL on stdout, one finding per line.
Exit code: 0 always (this is a *reporter*, not a gate; wrap in CI
if you want to fail the build).
"""

from __future__ import annotations

import json
import sys
from typing import Any


ROUND_CAPS = (1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072)
MAD_K = 6.0
MIN_MEDIAN_FOR_LOW_OUTLIER = 64
RUN_DECAY_MIN_LEN = 3
RUN_DECAY_MAX_RATIO = 0.5
VARIANCE_COLLAPSE_MIN_CALLS = 5


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _mad(xs: list[float], med: float) -> float:
    devs = [abs(x - med) for x in xs]
    return _median(devs)


def _near_round_cap(n: int) -> int | None:
    for cap in ROUND_CAPS:
        if n == 0:
            continue
        # within 1% below the cap, or exactly on it
        if cap - max(1, cap // 100) <= n <= cap:
            return cap
    return None


def _emit(findings: list[dict[str, Any]], **kw: Any) -> None:
    findings.append(kw)


def _check_tool(tool: str, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    sizes = [int(c["output_bytes"]) for c in calls]

    # 1. empty_output (per call)
    for c in calls:
        if int(c["output_bytes"]) == 0:
            _emit(
                findings,
                tool=tool,
                call_index=int(c["call_index"]),
                kind="empty_output",
                detail="output_bytes==0",
            )

    # 2/3. distribution outliers via median + MAD
    med = _median([float(s) for s in sizes])
    mad = _mad([float(s) for s in sizes], med)
    if mad > 0:
        hi = med + MAD_K * mad
        lo = med - MAD_K * mad
        for c in calls:
            n = int(c["output_bytes"])
            if n == 0:
                continue  # already covered
            if n > hi:
                _emit(
                    findings,
                    tool=tool,
                    call_index=int(c["call_index"]),
                    kind="size_outlier_high",
                    detail=f"bytes={n} median={med:g} mad={mad:g} threshold>{hi:g}",
                )
            elif n < lo and med > MIN_MEDIAN_FOR_LOW_OUTLIER and n >= 1:
                _emit(
                    findings,
                    tool=tool,
                    call_index=int(c["call_index"]),
                    kind="size_outlier_low",
                    detail=f"bytes={n} median={med:g} mad={mad:g} threshold<{lo:g}",
                )

    # 4. round-cap truncation (per call)
    for c in calls:
        n = int(c["output_bytes"])
        cap = _near_round_cap(n)
        if cap is not None:
            _emit(
                findings,
                tool=tool,
                call_index=int(c["call_index"]),
                kind="size_at_round_cap",
                detail=f"bytes={n} cap={cap}",
            )

    # 5. monotone decay run (>=3 strictly decreasing AND last < 50% first)
    i = 0
    while i < len(calls):
        j = i + 1
        while (
            j < len(calls)
            and int(calls[j]["output_bytes"]) < int(calls[j - 1]["output_bytes"])
        ):
            j += 1
        run_len = j - i
        if run_len >= RUN_DECAY_MIN_LEN:
            first = int(calls[i]["output_bytes"])
            last = int(calls[j - 1]["output_bytes"])
            if first > 0 and last < first * RUN_DECAY_MAX_RATIO:
                _emit(
                    findings,
                    tool=tool,
                    call_index=int(calls[i]["call_index"]),
                    kind="size_run_monotone_decay",
                    detail=(
                        f"run_len={run_len} "
                        f"first_bytes={first} last_bytes={last} "
                        f"last_call_index={int(calls[j - 1]['call_index'])}"
                    ),
                )
            i = j
        else:
            i += 1

    # 6. variance collapse
    if len(calls) >= VARIANCE_COLLAPSE_MIN_CALLS and len(set(sizes)) == 1:
        _emit(
            findings,
            tool=tool,
            call_index=int(calls[0]["call_index"]),
            kind="size_variance_collapse",
            detail=f"calls={len(calls)} bytes={sizes[0]}",
        )

    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: checker.py TRACE.jsonl", file=sys.stderr)
        return 2

    by_tool: dict[str, list[dict[str, Any]]] = {}
    with open(argv[1], "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            tool = str(obj["tool"])
            by_tool.setdefault(tool, []).append(obj)

    # keep insertion-stable order within tool by call_index
    for tool in by_tool:
        by_tool[tool].sort(key=lambda c: int(c["call_index"]))

    all_findings: list[dict[str, Any]] = []
    for tool in sorted(by_tool.keys()):
        all_findings.extend(_check_tool(tool, by_tool[tool]))

    # deterministic sort: tool, call_index, kind
    all_findings.sort(key=lambda f: (f["tool"], f["call_index"], f["kind"]))
    for f in all_findings:
        print(json.dumps(f, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

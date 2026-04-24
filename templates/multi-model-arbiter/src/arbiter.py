"""multi-model-arbiter

Route the SAME prompt to N candidate models, score the responses with
a pluggable criterion function, and return the winner plus a full
trace of who-said-what and why.

Pure stdlib. The model client is an injected callable so this module
never knows or cares which provider you use.

Public API:
    arbitrate(prompt, models, model_call, criterion, *, label=None)
        -> ArbitrationResult

Where:
    models       : list[str]
    model_call   : callable(model_name, prompt) -> str
    criterion    : callable(prompt, response) -> tuple[float, dict]
                   returns (score, evidence_dict). Higher score wins.
                   evidence is free-form JSON-serializable detail.

Why a pluggable criterion?  Because "best response" is task-specific:
    - For JSON extraction: criterion = does it parse + schema match.
    - For code: criterion = does it import + pass a smoke test.
    - For summary: criterion = length within band + keyword recall.
    - For multi-judge: criterion = mean of N rubric scores.
You compose the criterion; the arbiter just orchestrates.

Tie-breaking is deterministic: highest score wins; on tie, the model
listed first in `models` wins. Predictable > clever.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable


@dataclass
class CandidateRun:
    model: str
    response: str
    score: float
    evidence: dict
    elapsed_ms: int
    error: str | None = None


@dataclass
class ArbitrationResult:
    label: str | None
    prompt: str
    winner: str
    winner_score: float
    candidates: list[CandidateRun] = field(default_factory=list)
    decided_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, default=str)


def arbitrate(
    prompt: str,
    models: Iterable[str],
    model_call: Callable[[str, str], str],
    criterion: Callable[[str, str], tuple[float, dict]],
    *,
    label: str | None = None,
) -> ArbitrationResult:
    models = list(models)
    if not models:
        raise ValueError("at least one model is required")

    runs: list[CandidateRun] = []
    for m in models:
        t0 = time.perf_counter()
        try:
            resp = model_call(m, prompt)
            elapsed = int((time.perf_counter() - t0) * 1000)
            score, evidence = criterion(prompt, resp)
            runs.append(CandidateRun(m, resp, score, evidence, elapsed))
        except Exception as exc:  # noqa: BLE001 — caller-defined client
            elapsed = int((time.perf_counter() - t0) * 1000)
            runs.append(
                CandidateRun(
                    model=m,
                    response="",
                    score=float("-inf"),
                    evidence={"error_type": type(exc).__name__},
                    elapsed_ms=elapsed,
                    error=str(exc),
                )
            )

    # Highest score wins; ties go to first in input order (stable sort).
    indexed = list(enumerate(runs))
    indexed.sort(key=lambda pair: (-pair[1].score, pair[0]))
    winner_run = indexed[0][1]

    return ArbitrationResult(
        label=label,
        prompt=prompt,
        winner=winner_run.model,
        winner_score=winner_run.score,
        candidates=runs,
    )

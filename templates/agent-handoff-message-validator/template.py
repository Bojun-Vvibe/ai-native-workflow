"""Agent handoff message validator.

Validates the JSON envelope one agent passes to another at a handoff
boundary (e.g. scout -> actor, planner -> implementer, implementer ->
reviewer). Catches structural and semantic problems that would otherwise
silently corrupt the downstream agent's context window.

Distinct from `agent-handoff-protocol` (which defines the *transport*
envelope `done`/`partial`/`unrecoverable`). This template validates the
*payload* an upstream agent hands the next one: required fields, type
shape, length budgets, banned-token leaks, and reference integrity.

Pure stdlib. Returns a structured `ValidationResult` with errors and
warnings; never raises on bad input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


# Required top-level fields and their expected types.
REQUIRED_FIELDS: dict[str, type] = {
    "from_agent": str,
    "to_agent": str,
    "task_id": str,
    "summary": str,
    "next_action": str,
    "artifacts": list,
    "open_questions": list,
}

# Soft length budgets (chars). Above warn, above hard -> error.
SUMMARY_WARN_CHARS = 1500
SUMMARY_HARD_CHARS = 4000
QUESTION_WARN_CHARS = 400

# Allowed values for next_action.
ALLOWED_NEXT_ACTIONS = {"implement", "review", "investigate", "ask_human", "stop"}

# task_id format: alphanumeric + dash/underscore, 4..64 chars.
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")


def validate_handoff(
    msg: Any,
    *,
    banned_tokens: list[str] | None = None,
) -> ValidationResult:
    """Validate a handoff envelope. Never raises.

    `banned_tokens` is an optional list of substrings that must not appear
    anywhere in stringy fields (e.g. internal codenames, secrets prefixes).
    Match is case-insensitive.
    """
    result = ValidationResult(ok=True)
    banned = [b.lower() for b in (banned_tokens or [])]

    if not isinstance(msg, dict):
        result.add_error(f"top-level handoff must be a dict, got {type(msg).__name__}")
        return result

    # Required fields + types
    for field_name, expected_type in REQUIRED_FIELDS.items():
        if field_name not in msg:
            result.add_error(f"missing required field: {field_name}")
            continue
        if not isinstance(msg[field_name], expected_type):
            result.add_error(
                f"field {field_name!r}: expected {expected_type.__name__}, "
                f"got {type(msg[field_name]).__name__}"
            )

    if not result.ok:
        # Don't go deeper on structural failures; downstream checks would crash.
        return result

    # from_agent != to_agent
    if msg["from_agent"] == msg["to_agent"]:
        result.add_error(f"from_agent and to_agent are identical: {msg['from_agent']!r}")

    # task_id format
    if not TASK_ID_RE.match(msg["task_id"]):
        result.add_error(f"task_id {msg['task_id']!r} does not match {TASK_ID_RE.pattern}")

    # next_action enum
    if msg["next_action"] not in ALLOWED_NEXT_ACTIONS:
        result.add_error(
            f"next_action {msg['next_action']!r} not in {sorted(ALLOWED_NEXT_ACTIONS)}"
        )

    # Summary length
    s_len = len(msg["summary"])
    if s_len == 0:
        result.add_error("summary is empty")
    elif s_len > SUMMARY_HARD_CHARS:
        result.add_error(f"summary too long: {s_len} chars > {SUMMARY_HARD_CHARS}")
    elif s_len > SUMMARY_WARN_CHARS:
        result.add_warning(f"summary is long: {s_len} chars > {SUMMARY_WARN_CHARS}")

    # Open questions: each must be non-empty string, soft cap on length
    for i, q in enumerate(msg["open_questions"]):
        if not isinstance(q, str):
            result.add_error(f"open_questions[{i}]: expected str, got {type(q).__name__}")
            continue
        if not q.strip():
            result.add_error(f"open_questions[{i}]: empty / whitespace only")
            continue
        if len(q) > QUESTION_WARN_CHARS:
            result.add_warning(f"open_questions[{i}]: {len(q)} chars > {QUESTION_WARN_CHARS}")

    # Artifacts: each must be {"kind": str, "ref": str}
    artifact_refs: set[str] = set()
    for i, a in enumerate(msg["artifacts"]):
        if not isinstance(a, dict):
            result.add_error(f"artifacts[{i}]: expected object, got {type(a).__name__}")
            continue
        for k in ("kind", "ref"):
            if k not in a:
                result.add_error(f"artifacts[{i}]: missing key {k!r}")
            elif not isinstance(a[k], str) or not a[k].strip():
                result.add_error(f"artifacts[{i}].{k}: must be non-empty string")
        ref = a.get("ref")
        if isinstance(ref, str):
            if ref in artifact_refs:
                result.add_warning(f"artifacts[{i}]: duplicate ref {ref!r}")
            artifact_refs.add(ref)

    # Reference integrity: any "see artifact:<ref>" mentions in summary must resolve
    for m in re.finditer(r"artifact:([A-Za-z0-9_\-./]+)", msg["summary"]):
        ref = m.group(1)
        if ref not in artifact_refs:
            result.add_error(f"summary references unknown artifact:{ref}")

    # Banned tokens scan over all stringy content
    if banned:
        def _scan(text: str, where: str) -> None:
            low = text.lower()
            for tok in banned:
                if tok in low:
                    result.add_error(f"banned token {tok!r} found in {where}")

        _scan(msg["summary"], "summary")
        for i, q in enumerate(msg["open_questions"]):
            if isinstance(q, str):
                _scan(q, f"open_questions[{i}]")
        for i, a in enumerate(msg["artifacts"]):
            if isinstance(a, dict):
                for k, v in a.items():
                    if isinstance(v, str):
                        _scan(v, f"artifacts[{i}].{k}")

    return result

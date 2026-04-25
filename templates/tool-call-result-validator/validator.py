"""Validate tool-call results against a declared schema before feeding back to the LLM.

Why: LLMs hallucinate around malformed tool output. Catching shape drift at the
boundary prevents the next turn from inheriting garbage. Returns a (report, safe)
tuple so callers can log the diff and still hand a sanitized payload upstream.

Stdlib only. No third-party deps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FieldSpec:
    name: str
    type: type
    required: bool = True
    coerce: Callable[[Any], Any] | None = None  # optional coercion (e.g. str->int)


@dataclass
class ResultSchema:
    tool_name: str
    fields: list[FieldSpec]
    allow_extra: bool = False  # if False, extra keys are stripped from "safe"


@dataclass
class ValidationReport:
    tool_name: str
    ok: bool
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    type_errors: list[str] = field(default_factory=list)
    coerced: list[str] = field(default_factory=list)

    def render(self) -> str:
        status = "OK" if self.ok else "FAIL"
        lines = [f"[{status}] tool={self.tool_name}"]
        if self.missing:
            lines.append(f"  missing required: {self.missing}")
        if self.extra:
            lines.append(f"  extra fields:     {self.extra}")
        if self.type_errors:
            lines.append(f"  type errors:      {self.type_errors}")
        if self.coerced:
            lines.append(f"  coerced:          {self.coerced}")
        return "\n".join(lines)


def validate(result: dict[str, Any], schema: ResultSchema) -> tuple[ValidationReport, dict[str, Any]]:
    """Validate `result` against `schema`. Returns (report, safe_subset).

    `safe_subset` is what you should hand back to the LLM — required fields only,
    coerced where possible, extras dropped unless `schema.allow_extra` is True.
    """
    report = ValidationReport(tool_name=schema.tool_name, ok=True)
    safe: dict[str, Any] = {}
    declared = {f.name for f in schema.fields}

    for spec in schema.fields:
        if spec.name not in result:
            if spec.required:
                report.missing.append(spec.name)
                report.ok = False
            continue
        value = result[spec.name]
        if not isinstance(value, spec.type):
            if spec.coerce is not None:
                try:
                    value = spec.coerce(value)
                    report.coerced.append(spec.name)
                except Exception:
                    report.type_errors.append(
                        f"{spec.name}: expected {spec.type.__name__}, got {type(value).__name__}"
                    )
                    report.ok = False
                    continue
            else:
                report.type_errors.append(
                    f"{spec.name}: expected {spec.type.__name__}, got {type(value).__name__}"
                )
                report.ok = False
                continue
        safe[spec.name] = value

    for key in result:
        if key not in declared:
            report.extra.append(key)
            if schema.allow_extra:
                safe[key] = result[key]

    return report, safe

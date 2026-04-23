"""
Agent output validator.

Three policies:
  - "reject":      raise ValidationError on any failure.
  - "repair_once": if structurally JSON but schema-invalid, return a
                   RepairRequest the orchestrator can pass to a single
                   repair turn. If still invalid after repair, reject.
  - "quarantine":  on failure, write the bad output to a quarantine
                   path and return None so the parent can continue.

Stdlib only by default. Falls back to a minimal manual validator if
`jsonschema` is not installed (handles `type`, `required`, `enum`,
`additionalProperties`, nested `properties` and `items`).
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import jsonschema  # type: ignore

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    _HAS_JSONSCHEMA = False


MAX_REPAIR_ATTEMPTS = 1
QUARANTINE_DIR = Path(os.environ.get("AGENT_QUARANTINE_DIR", "/tmp/agent-quarantine"))


class ValidationError(Exception):
    pass


@dataclass
class RepairRequest:
    """Returned by `repair_once` policy when output needs a fix turn."""

    original: str
    error: str
    schema: dict
    attempt: int = 0


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_fences(s: str) -> str:
    m = _FENCE_RE.match(s)
    return m.group(1) if m else s


def _try_parse(raw: str) -> tuple[Any | None, str | None]:
    """Return (parsed, None) or (None, error_message)."""
    candidate = _strip_fences(raw.strip())
    try:
        return json.loads(candidate), None
    except json.JSONDecodeError as e:
        return None, f"json parse error at line {e.lineno} col {e.colno}: {e.msg}"


def _manual_validate(data: Any, schema: dict, path: str = "$") -> str | None:
    """Minimal validator. Returns None on success, or an error string."""
    t = schema.get("type")
    if t == "object":
        if not isinstance(data, dict):
            return f"{path}: expected object, got {type(data).__name__}"
        required = schema.get("required", [])
        for r in required:
            if r not in data:
                return f"{path}: required field '{r}' missing"
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            for k in data.keys():
                if k not in allowed:
                    return f"{path}: unexpected field '{k}' (additionalProperties:false)"
        for k, sub in schema.get("properties", {}).items():
            if k in data:
                err = _manual_validate(data[k], sub, f"{path}.{k}")
                if err:
                    return err
    elif t == "array":
        if not isinstance(data, list):
            return f"{path}: expected array, got {type(data).__name__}"
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(data):
                err = _manual_validate(item, item_schema, f"{path}[{i}]")
                if err:
                    return err
    elif t == "string":
        if not isinstance(data, str):
            return f"{path}: expected string, got {type(data).__name__}"
        if "enum" in schema and data not in schema["enum"]:
            return f"{path}: value {data!r} not in enum {schema['enum']}"
    elif t == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            return f"{path}: expected integer, got {type(data).__name__}"
    elif t == "boolean":
        if not isinstance(data, bool):
            return f"{path}: expected boolean, got {type(data).__name__}"
    return None


def _validate_against_schema(data: Any, schema: dict) -> str | None:
    if _HAS_JSONSCHEMA:
        try:
            jsonschema.validate(data, schema)
            return None
        except jsonschema.ValidationError as e:
            path = "$" + "".join(f".{p}" if isinstance(p, str) else f"[{p}]" for p in e.absolute_path)
            return f"{path}: {e.message}"
    return _manual_validate(data, schema)


def _quarantine(raw: str, error: str) -> Path:
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    qid = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    path = QUARANTINE_DIR / f"{qid}.json"
    path.write_text(json.dumps({"error": error, "raw": raw}, indent=2))
    return path


def validate(
    raw_output: str,
    schema: dict,
    policy: str = "reject",
) -> Any | RepairRequest | None:
    """Validate a sub-agent's raw text output against `schema`.

    Returns:
      - parsed dict/list on success
      - RepairRequest if policy=="repair_once" and the output is
        structurally JSON but schema-invalid
      - None if policy=="quarantine" and the output is bad
    Raises ValidationError if policy=="reject" and the output is bad.
    """
    parsed, parse_err = _try_parse(raw_output)
    if parse_err:
        return _handle_failure(raw_output, parse_err, schema, policy, structural=True)

    schema_err = _validate_against_schema(parsed, schema)
    if schema_err is None:
        return parsed
    return _handle_failure(raw_output, f"schema: {schema_err}", schema, policy, structural=False)


def _handle_failure(
    raw: str,
    error: str,
    schema: dict,
    policy: str,
    structural: bool,
) -> RepairRequest | None:
    if policy == "reject":
        raise ValidationError(error)
    if policy == "repair_once":
        # Structural (unparseable) failures get one repair attempt too.
        return RepairRequest(original=raw, error=error, schema=schema, attempt=0)
    if policy == "quarantine":
        path = _quarantine(raw, error)
        print(f"[quarantine] {error} → {path}")
        return None
    raise ValueError(f"unknown policy: {policy}")


def apply_repair(req: RepairRequest, repaired_raw: str) -> Any:
    """Validate the repair attempt. Always strict on second pass."""
    if req.attempt >= MAX_REPAIR_ATTEMPTS:
        raise ValidationError(f"repair budget exhausted ({req.attempt} attempts)")
    parsed, parse_err = _try_parse(repaired_raw)
    if parse_err:
        raise ValidationError(f"repair failed (parse): {parse_err}")
    schema_err = _validate_against_schema(parsed, req.schema)
    if schema_err:
        raise ValidationError(f"repair failed (schema): {schema_err}")
    return parsed

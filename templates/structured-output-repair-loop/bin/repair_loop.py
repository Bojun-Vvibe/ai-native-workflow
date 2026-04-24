#!/usr/bin/env python3
"""Reference repair-loop implementation. Stdlib only.

Reads a scenario JSON describing the prompt, JSON Schema, and a
canned mock-model script (list of outputs the mock returns in
order across attempts). Runs the repair loop and prints the exit
state.

Usage:
    python3 repair_loop.py SCENARIO.json

Scenario shape:
    {
      "prompt": "...",
      "schema": { ... mini-schema, see _validate ... },
      "mock_outputs": ["{...}", "{...}", ...],
      "max_attempts": 4,
      "deadline_ms": 30000
    }

Exit status JSON has shape:
    {
      "status": "parsed" | "stuck" | "exhausted",
      "attempts": N,
      "fingerprints_seen": ["...", "..."],
      "parsed_value": { ... } | null,
      "last_error": { ... } | null,
      "last_raw_output": "..." | null
    }

The mini-schema validator supports:
  - {"type": "object", "required": [...], "properties": {...},
     "additional_properties": false|true}
  - {"type": "string", "pattern": "regex", "enum": [...]}
  - {"type": "integer"}, {"type": "number"}, {"type": "boolean"}
  - {"type": "array", "items": <schema>}
This is intentionally minimal; production callers should swap in
jsonschema or pydantic. The loop *algorithm* doesn't change.
"""
from __future__ import annotations

import json
import re
import sys
import time
from typing import Any

# Allow running from any cwd.
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from error_fingerprint import fingerprint  # noqa: E402
from render_hint import render_hint  # noqa: E402


# ---------- Mini-validator ----------------------------------------

class ValidationError(Exception):
    def __init__(self, error_class: str, json_pointer: str,
                 expected: str, got: Any):
        self.error_class = error_class
        self.json_pointer = json_pointer
        self.expected = expected
        self.got = got
        super().__init__(f"{error_class} at {json_pointer}: expected "
                         f"{expected}, got {got!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_class": self.error_class,
            "json_pointer": self.json_pointer,
            "expected": self.expected,
            "got": self.got,
        }


def _validate(value: Any, schema: dict[str, Any], pointer: str = "") -> None:
    t = schema.get("type")
    if t == "object":
        if not isinstance(value, dict):
            raise ValidationError("TypeMismatch", pointer or "/", "object",
                                  type(value).__name__)
        for req in schema.get("required", []):
            if req not in value:
                raise ValidationError("MissingField",
                                      f"{pointer}/{req}", "present", None)
        if not schema.get("additional_properties", True):
            allowed = set(schema.get("properties", {}).keys())
            for k in value:
                if k not in allowed:
                    raise ValidationError("ExtraField",
                                          f"{pointer}/{k}",
                                          f"one of {sorted(allowed)}", k)
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                _validate(value[k], sub, f"{pointer}/{k}")
    elif t == "string":
        if not isinstance(value, str):
            raise ValidationError("TypeMismatch", pointer or "/", "string",
                                  type(value).__name__)
        pat = schema.get("pattern")
        if pat and not re.search(pat, value):
            raise ValidationError("SchemaValidationError", pointer or "/",
                                  f"string matching {pat}", value)
        en = schema.get("enum")
        if en is not None and value not in en:
            raise ValidationError("EnumViolation", pointer or "/",
                                  ", ".join(repr(x) for x in en), value)
    elif t == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError("TypeMismatch", pointer or "/", "integer",
                                  type(value).__name__)
    elif t == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError("TypeMismatch", pointer or "/", "number",
                                  type(value).__name__)
    elif t == "boolean":
        if not isinstance(value, bool):
            raise ValidationError("TypeMismatch", pointer or "/", "boolean",
                                  type(value).__name__)
    elif t == "array":
        if not isinstance(value, list):
            raise ValidationError("TypeMismatch", pointer or "/", "array",
                                  type(value).__name__)
        item_schema = schema.get("items", {})
        for i, item in enumerate(value):
            _validate(item, item_schema, f"{pointer}/{i}")
    # unknown types: pass through (extension point)


# ---------- Mock model --------------------------------------------

class MockModel:
    """Returns the next canned output. Replace with your SDK call."""

    def __init__(self, outputs: list[str]):
        self._outputs = list(outputs)
        self._idx = 0

    def complete(self, prompt: str) -> str:
        if self._idx >= len(self._outputs):
            # Repeat last output forever (simulates "stuck" model).
            return self._outputs[-1] if self._outputs else "{}"
        out = self._outputs[self._idx]
        self._idx += 1
        return out


# ---------- The loop ----------------------------------------------

def run_repair_loop(prompt: str, schema: dict[str, Any], model: MockModel,
                    max_attempts: int = 4,
                    deadline_ms: int = 30_000) -> dict[str, Any]:
    started_at = time.monotonic()
    fingerprints_seen: list[str] = []
    attempt = 1
    last_raw = None
    last_err: ValidationError | None = None
    current_prompt = prompt

    while attempt <= max_attempts:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        if elapsed_ms > deadline_ms:
            return _result("expired", attempt - 1, fingerprints_seen,
                           None, last_err, last_raw)

        raw = model.complete(current_prompt)
        last_raw = raw

        # Parse JSON.
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as e:
            err = ValidationError("JSONDecodeError", "/",
                                  "valid JSON", str(e))
            last_err = err
            fp = fingerprint(err.to_dict())
            if fp in fingerprints_seen:
                return _result("stuck", attempt, fingerprints_seen,
                               None, err, raw)
            fingerprints_seen.append(fp)
            current_prompt = _build_repair_prompt(prompt, raw, err)
            attempt += 1
            continue

        # Schema validate.
        try:
            _validate(value, schema)
            return _result("parsed", attempt, fingerprints_seen,
                           value, None, raw)
        except ValidationError as e:
            last_err = e
            fp = fingerprint(e.to_dict())
            if fp in fingerprints_seen:
                return _result("stuck", attempt, fingerprints_seen,
                               None, e, raw)
            fingerprints_seen.append(fp)
            current_prompt = _build_repair_prompt(prompt, raw, e)
            attempt += 1

    return _result("exhausted", max_attempts, fingerprints_seen,
                   None, last_err, last_raw)


def _build_repair_prompt(original: str, prev_output: str,
                         err: ValidationError) -> str:
    return (f"{original}\n\n"
            f"--- Previous attempt output ---\n{prev_output}\n"
            f"--- End previous attempt ---\n\n"
            f"{render_hint(err.to_dict())}\n")


def _result(status: str, attempts: int, fps: list[str],
            value: Any, err: ValidationError | None,
            raw: str | None) -> dict[str, Any]:
    return {
        "status": status,
        "attempts": attempts,
        "fingerprints_seen": fps,
        "parsed_value": value,
        "last_error": err.to_dict() if err else None,
        "last_raw_output": raw,
    }


# ---------- Entry point -------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: repair_loop.py SCENARIO.json", file=sys.stderr)
        return 2
    with open(argv[1]) as f:
        scenario = json.load(f)
    model = MockModel(scenario["mock_outputs"])
    result = run_repair_loop(
        prompt=scenario["prompt"],
        schema=scenario["schema"],
        model=model,
        max_attempts=scenario.get("max_attempts", 4),
        deadline_ms=scenario.get("deadline_ms", 30_000),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

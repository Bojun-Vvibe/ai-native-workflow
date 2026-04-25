"""
Coerce loose LLM-emitted tool-call arguments into a strict schema before
the host actually invokes the tool.

Models emit arguments that are *almost* right: a string where an int is
needed, `null` where the schema has a default, a stringified bool, an
ISO date as a string instead of an epoch second. Rejecting outright
forces an extra round-trip; accepting blindly causes downstream
TypeErrors. The coercer lives between the model and the tool dispatch:

  model output dict  ->  coerce(schema, args)  ->  CoerceResult
                                                     |
                                       OK -> dispatch tool with .args
                                       FAIL -> hand structured errors
                                               back to the model for
                                               a single repair turn

Stdlib only. No jsonschema dependency. Schemas are tiny dicts:

  {
    "field_name": {
      "type": "int" | "float" | "bool" | "str" | "epoch_seconds",
      "required": True/False,
      "default": <value>,        # used when missing/null AND not required
      "min": <num>, "max": <num> # optional bounds for numeric/epoch
    }
  }
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Coercion is conservative: only well-known mappings.
_TRUTHY = {"true", "t", "yes", "y", "1", "on"}
_FALSY = {"false", "f", "no", "n", "0", "off"}


@dataclass
class FieldError:
    field: str
    reason: str
    got: Any


@dataclass
class CoerceResult:
    ok: bool
    args: Dict[str, Any]                 # final coerced arg dict (only valid if ok)
    errors: List[FieldError] = field(default_factory=list)
    coerced_fields: List[str] = field(default_factory=list)  # fields whose value was changed
    defaulted_fields: List[str] = field(default_factory=list)
    unknown_fields: List[str] = field(default_factory=list)  # fields in input but not schema

    def repair_prompt(self) -> str:
        """Build a structured repair instruction the model can act on."""
        if self.ok:
            return ""
        lines = ["Your tool call had argument errors. Fix and resend:"]
        for e in self.errors:
            lines.append(f"  - field {e.field!r}: {e.reason} (got: {e.got!r})")
        if self.unknown_fields:
            lines.append(
                f"  - unknown fields (drop them): {self.unknown_fields}"
            )
        return "\n".join(lines)


def coerce(schema: Dict[str, Dict[str, Any]],
           args: Dict[str, Any]) -> CoerceResult:
    out: Dict[str, Any] = {}
    errors: List[FieldError] = []
    coerced: List[str] = []
    defaulted: List[str] = []

    schema_fields = set(schema.keys())
    input_fields = set(args.keys())
    unknown = sorted(input_fields - schema_fields)

    for fname, spec in schema.items():
        ftype = spec["type"]
        required = spec.get("required", False)
        has_default = "default" in spec
        raw = args.get(fname, _MISSING)

        # Missing / null handling
        if raw is _MISSING or raw is None:
            if has_default:
                out[fname] = spec["default"]
                defaulted.append(fname)
                continue
            if required:
                errors.append(FieldError(fname, "required field missing", raw))
                continue
            # not required, no default -> omit
            continue

        # Type coercion
        try:
            value, did_coerce = _coerce_value(raw, ftype)
        except _CoerceFail as e:
            errors.append(FieldError(fname, e.reason, raw))
            continue

        # Bounds
        bound_err = _check_bounds(value, spec)
        if bound_err is not None:
            errors.append(FieldError(fname, bound_err, raw))
            continue

        out[fname] = value
        if did_coerce:
            coerced.append(fname)

    return CoerceResult(
        ok=(len(errors) == 0),
        args=out if len(errors) == 0 else {},
        errors=errors,
        coerced_fields=coerced,
        defaulted_fields=defaulted,
        unknown_fields=unknown,
    )


# --- internals ---

class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


_MISSING = _Missing()


class _CoerceFail(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _coerce_value(raw: Any, ftype: str) -> Tuple[Any, bool]:
    if ftype == "int":
        if isinstance(raw, bool):  # bool is a subclass of int; reject ambiguity
            raise _CoerceFail("expected int, got bool")
        if isinstance(raw, int):
            return raw, False
        if isinstance(raw, float):
            if raw.is_integer():
                return int(raw), True
            raise _CoerceFail("expected int, got non-integer float")
        if isinstance(raw, str):
            s = raw.strip()
            try:
                return int(s), True
            except ValueError:
                raise _CoerceFail("expected int, string is not numeric")
        raise _CoerceFail(f"expected int, got {type(raw).__name__}")

    if ftype == "float":
        if isinstance(raw, bool):
            raise _CoerceFail("expected float, got bool")
        if isinstance(raw, (int, float)):
            return float(raw), not isinstance(raw, float)
        if isinstance(raw, str):
            try:
                return float(raw.strip()), True
            except ValueError:
                raise _CoerceFail("expected float, string is not numeric")
        raise _CoerceFail(f"expected float, got {type(raw).__name__}")

    if ftype == "bool":
        if isinstance(raw, bool):
            return raw, False
        if isinstance(raw, str):
            s = raw.strip().lower()
            if s in _TRUTHY:
                return True, True
            if s in _FALSY:
                return False, True
            raise _CoerceFail("expected bool, string not in known truthy/falsy set")
        if isinstance(raw, int) and raw in (0, 1):
            return bool(raw), True
        raise _CoerceFail(f"expected bool, got {type(raw).__name__}")

    if ftype == "str":
        if isinstance(raw, str):
            return raw, False
        # Avoid stringifying complex types — too lossy.
        if isinstance(raw, (int, float, bool)):
            return str(raw), True
        raise _CoerceFail(f"expected str, got {type(raw).__name__}")

    if ftype == "epoch_seconds":
        if isinstance(raw, bool):
            raise _CoerceFail("expected epoch_seconds, got bool")
        if isinstance(raw, int):
            return raw, False
        if isinstance(raw, float) and raw.is_integer():
            return int(raw), True
        if isinstance(raw, str):
            s = raw.strip()
            # Numeric string?
            try:
                return int(s), True
            except ValueError:
                pass
            # ISO-8601?
            try:
                if s.endswith("Z"):
                    s2 = s[:-1] + "+00:00"
                else:
                    s2 = s
                dt = _dt.datetime.fromisoformat(s2)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_dt.timezone.utc)
                return int(dt.timestamp()), True
            except ValueError:
                raise _CoerceFail("expected epoch_seconds, unparseable date string")
        raise _CoerceFail(f"expected epoch_seconds, got {type(raw).__name__}")

    raise _CoerceFail(f"unknown schema type: {ftype}")


def _check_bounds(value: Any, spec: Dict[str, Any]) -> Optional[str]:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    if "min" in spec and value < spec["min"]:
        return f"value {value} below min {spec['min']}"
    if "max" in spec and value > spec["max"]:
        return f"value {value} above max {spec['max']}"
    return None

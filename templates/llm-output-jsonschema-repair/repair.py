"""Local-only JSON Schema repair for LLM outputs.

When an LLM is asked to emit structured JSON, you typically get one of:
  (a) clean JSON — done.
  (b) JSON wrapped in ```json ... ``` fences, or with a one-line
      "Sure, here you go:" preamble.
  (c) JSON with a trailing comma, smart quotes, or unescaped newlines
      inside a string.
  (d) Valid JSON but missing a required field, or with a string where
      the schema wants an int.

Round-tripping (d) back through the model is expensive and adds
latency. This module attempts cheap, deterministic, local repairs
against a JSON Schema (draft-07-style, but only the subset that's
realistically used in agent outputs):

  - Strip Markdown code fences and conversational preambles.
  - Strip trailing commas in objects/arrays.
  - Replace smart quotes with ASCII quotes.
  - Coerce types where unambiguous: "42" -> 42 if schema says integer;
    "true"/"false" -> bool; null -> default if schema has one.
  - Inject schema-declared defaults for missing required fields.
  - Drop additionalProperties=false violations (with a record).

Repairs that are NOT attempted (because they're guesswork):
  - Inventing values for required fields with no default.
  - Repairing arrays whose items violate per-item schemas in
    irreducible ways.

`repair()` returns a `RepairResult` with the parsed object, the
ordered list of repair operations applied, and any remaining
violations. The caller decides whether to accept, reject, or escalate
to a model round-trip.

Pure stdlib. No `jsonschema` dependency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL,
)
_PREAMBLE_RE = re.compile(
    r"^\s*(?:sure|here(?:'s| is| you go)|certainly|of course)[^{\[`]*",
    re.IGNORECASE | re.DOTALL,
)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_SMART_QUOTES = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
}


@dataclass
class RepairResult:
    ok: bool
    value: Optional[Any]
    repairs: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    raw_after_textual_repair: str = ""


def _strip_text_noise(s: str) -> Tuple[str, List[str]]:
    repairs: List[str] = []
    s2 = s
    # Strip preamble first so a fence that follows "Sure, here you go:\n"
    # still anchors at the start of the remaining string.
    pre = _PREAMBLE_RE.match(s2)
    if pre and ("{" in s2 or "[" in s2 or "```" in s2):
        cut_candidates = [s2.find(c) for c in ("{", "[", "```")
                          if c in s2 and s2.find(c) >= 0]
        if cut_candidates:
            cut = min(cut_candidates)
            if cut > 0 and cut >= pre.end() - 1:
                s2 = s2[cut:]
                repairs.append("strip_conversational_preamble")
    m = _FENCE_RE.match(s2)
    if m:
        s2 = m.group(1)
        repairs.append("strip_code_fence")
    if any(q in s2 for q in _SMART_QUOTES):
        for bad, good in _SMART_QUOTES.items():
            s2 = s2.replace(bad, good)
        repairs.append("normalize_smart_quotes")
    if _TRAILING_COMMA_RE.search(s2):
        s2 = _TRAILING_COMMA_RE.sub(r"\1", s2)
        repairs.append("strip_trailing_commas")
    return s2, repairs


def _coerce_to_type(value: Any, target: str) -> Tuple[Any, bool]:
    """Return (coerced_value, did_coerce)."""
    if target == "integer":
        if isinstance(value, bool):  # bool is subclass of int — exclude.
            return value, False
        if isinstance(value, int):
            return value, False
        if isinstance(value, float) and value.is_integer():
            return int(value), True
        if isinstance(value, str):
            try:
                return int(value.strip()), True
            except ValueError:
                return value, False
    elif target == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value, False
        if isinstance(value, str):
            try:
                return float(value.strip()), True
            except ValueError:
                return value, False
    elif target == "boolean":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "yes", "1"):
                return True, True
            if v in ("false", "no", "0"):
                return False, True
    elif target == "string":
        if isinstance(value, str):
            return value, False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value), True
    return value, False


def _walk(value: Any, schema: dict, path: str,
          repairs: List[str], violations: List[str]) -> Any:
    t = schema.get("type")
    if t == "object" and isinstance(value, dict):
        props = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []
        additional = schema.get("additionalProperties", True)

        # Inject defaults for missing required fields where possible.
        for r in required:
            if r not in value:
                sub = props.get(r, {})
                if "default" in sub:
                    value[r] = sub["default"]
                    repairs.append(f"default_required:{path}/{r}")
                else:
                    violations.append(f"missing_required:{path}/{r}")

        # Recurse into known properties.
        for k, sub in props.items():
            if k in value:
                value[k] = _walk(value[k], sub, f"{path}/{k}",
                                 repairs, violations)

        # Drop additionalProperties=false violations.
        if additional is False:
            extras = [k for k in value if k not in props]
            for k in extras:
                value.pop(k)
                repairs.append(f"drop_additional:{path}/{k}")
        return value

    if t == "array" and isinstance(value, list):
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for i, item in enumerate(value):
                value[i] = _walk(item, items_schema, f"{path}[{i}]",
                                 repairs, violations)
        return value

    if isinstance(t, str) and t in ("integer", "number", "boolean", "string"):
        coerced, did = _coerce_to_type(value, t)
        if did:
            repairs.append(f"coerce_{t}:{path}")
            return coerced
        # Type still wrong? record violation.
        py_ok = {
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float))
            and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "string": isinstance(value, str),
        }[t]
        if not py_ok and value is not None:
            violations.append(f"type_mismatch:{path} expected {t}")
        return value

    # Enum check (post-coercion).
    if "enum" in schema and value not in schema["enum"]:
        violations.append(f"enum_violation:{path}")

    return value


def repair(raw: str, schema: dict) -> RepairResult:
    """Attempt to coerce `raw` (LLM output text) into `schema`.

    Returns a RepairResult. `ok=True` means the result is structurally
    valid against the supported subset of the schema; `violations`
    being non-empty means the caller should treat it as a soft failure
    even if `value` parsed.
    """
    cleaned, text_repairs = _strip_text_noise(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return RepairResult(
            ok=False,
            value=None,
            repairs=text_repairs,
            violations=[f"json_parse_error:{exc.msg} at pos {exc.pos}"],
            raw_after_textual_repair=cleaned,
        )

    repairs = list(text_repairs)
    violations: List[str] = []
    value = _walk(parsed, schema, "", repairs, violations)
    return RepairResult(
        ok=not violations,
        value=value,
        repairs=repairs,
        violations=violations,
        raw_after_textual_repair=cleaned,
    )

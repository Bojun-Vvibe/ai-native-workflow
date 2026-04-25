"""Per-required-field coverage reporter for a corpus of LLM JSON outputs.

Problem: you have a JSON schema with N required fields, and a corpus of M
candidate outputs from an LLM. Per-document validation tells you `M_pass /
M_fail`, but it does not tell you *which required field is the most common
reason for failure*. That is the signal you actually need to fix the prompt:
"the model forgets `summary` 38% of the time" is actionable; "73% pass" is not.

This template walks a (small subset of) JSON Schema and produces, per required
field path, the rates:

  present_rate         = present and not null and (if typed) of correct type
  missing_rate         = key absent
  null_rate            = key present but value is JSON null
  wrong_type_rate      = key present, not null, but wrong type for `type`

Plus a top-level summary:
  documents_total
  documents_all_required_present
  documents_with_at_least_one_missing
  worst_offender_path
  worst_offender_missing_rate

It is **not** a full JSON Schema validator — see Non-goals in the README. It
walks `properties`, `required`, `type`, and `items.properties` of nested
arrays of objects (the shape that 95% of LLM-output schemas use).

Stdlib only. Pure. Deterministic field-path ordering (depth-first, schema
declaration order).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Schema walker — collects (json_pointer_path, expected_type_or_None) for
# every required leaf, including required leaves inside required nested
# objects and inside `items` of required arrays of objects.
# ---------------------------------------------------------------------------

_TYPE_PY = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _required_paths(schema: dict, base: str = "") -> list[tuple[str, str | None]]:
    """Return the ordered list of (path, expected_type) for required leaves.

    `path` is a JSON-pointer-ish string like "/summary" or
    "/items[]/title". Paths under `items[]` mean: "for each element of the
    enclosing required array, the inner field is itself required".
    """
    out: list[tuple[str, str | None]] = []
    if not isinstance(schema, dict):
        return out
    if schema.get("type") != "object":
        return out
    required = schema.get("required") or []
    props = schema.get("properties") or {}
    for name in required:
        if name not in props:
            # required name with no schema entry — record as untyped required.
            out.append((f"{base}/{name}", None))
            continue
        sub = props[name]
        sub_type = sub.get("type") if isinstance(sub, dict) else None
        path = f"{base}/{name}"
        out.append((path, sub_type if isinstance(sub_type, str) else None))
        if sub_type == "object":
            out.extend(_required_paths(sub, path))
        elif sub_type == "array":
            items = sub.get("items") if isinstance(sub, dict) else None
            if isinstance(items, dict) and items.get("type") == "object":
                out.extend(_required_paths(items, f"{path}[]"))
    return out


# ---------------------------------------------------------------------------
# Per-document evaluation of one required path against one document.
# ---------------------------------------------------------------------------

_MISSING = "missing"
_NULL = "null"
_PRESENT = "present"
_WRONG_TYPE = "wrong_type"


def _check_path(doc: Any, path: str, expected_type: str | None) -> str:
    """Return one of {missing, null, present, wrong_type} for this doc.

    For paths under `[]` (array iteration), the document satisfies the path iff
    the enclosing array exists, is non-empty, and *every* element satisfies the
    inner path. An empty enclosing array counts as `missing`. A non-list
    enclosing value counts as `wrong_type` for the outer array (already
    surfaced by the outer path entry), and as `missing` for the inner one.
    """
    parts = [p for p in path.split("/") if p]
    return _walk(doc, parts, expected_type)


def _walk(node: Any, parts: list[str], expected_type: str | None) -> str:
    if not parts:
        # We've arrived at the value.
        if node is None:
            return _NULL
        if expected_type is not None:
            py = _TYPE_PY.get(expected_type)
            if py is not None and not isinstance(node, py):
                return _WRONG_TYPE
            # Special: bool is subclass of int in Python; reject silently.
            if expected_type == "integer" and isinstance(node, bool):
                return _WRONG_TYPE
        return _PRESENT

    head = parts[0]
    rest = parts[1:]
    if head.endswith("[]"):
        key = head[:-2]
        if not isinstance(node, dict) or key not in node:
            return _MISSING
        arr = node[key]
        if not isinstance(arr, list) or len(arr) == 0:
            return _MISSING
        # Aggregate: worst (in priority missing > wrong_type > null > present).
        prio = {_MISSING: 3, _WRONG_TYPE: 2, _NULL: 1, _PRESENT: 0}
        worst = _PRESENT
        for elem in arr:
            v = _walk(elem, rest, expected_type)
            if prio[v] > prio[worst]:
                worst = v
        return worst

    if not isinstance(node, dict):
        return _MISSING
    if head not in node:
        return _MISSING
    return _walk(node[head], rest, expected_type)


# ---------------------------------------------------------------------------
# Public report.
# ---------------------------------------------------------------------------


@dataclass
class FieldStat:
    path: str
    expected_type: str | None
    present: int = 0
    missing: int = 0
    null: int = 0
    wrong_type: int = 0

    def total(self) -> int:
        return self.present + self.missing + self.null + self.wrong_type

    def rate(self, n: int) -> dict:
        if n == 0:
            return {"present": 0.0, "missing": 0.0, "null": 0.0, "wrong_type": 0.0}
        return {
            "present": round(self.present / n, 4),
            "missing": round(self.missing / n, 4),
            "null": round(self.null / n, 4),
            "wrong_type": round(self.wrong_type / n, 4),
        }


@dataclass
class CoverageReport:
    documents_total: int
    documents_all_required_present: int
    documents_with_at_least_one_missing: int
    fields: list[FieldStat] = field(default_factory=list)

    @property
    def worst_offender(self) -> FieldStat | None:
        # "Worst" = highest missing+null+wrong_type rate. Ties broken by schema
        # declaration order (which is `fields` order).
        if not self.fields or self.documents_total == 0:
            return None
        n = self.documents_total
        return max(
            self.fields,
            key=lambda f: ((f.missing + f.null + f.wrong_type) / n, -self.fields.index(f)),
        )

    def to_dict(self) -> dict:
        n = self.documents_total
        worst = self.worst_offender
        return {
            "documents_total": self.documents_total,
            "documents_all_required_present": self.documents_all_required_present,
            "documents_with_at_least_one_missing": self.documents_with_at_least_one_missing,
            "worst_offender_path": worst.path if worst else None,
            "worst_offender_missing_rate": (
                round((worst.missing + worst.null + worst.wrong_type) / n, 4)
                if worst and n
                else 0.0
            ),
            "fields": [
                {
                    "path": f.path,
                    "expected_type": f.expected_type,
                    "counts": {
                        "present": f.present,
                        "missing": f.missing,
                        "null": f.null,
                        "wrong_type": f.wrong_type,
                    },
                    "rates": f.rate(n),
                }
                for f in self.fields
            ],
        }


def report(schema: dict, documents: list[Any]) -> CoverageReport:
    paths = _required_paths(schema)
    stats: dict[str, FieldStat] = {p: FieldStat(p, t) for p, t in paths}
    docs_all_ok = 0
    docs_any_missing = 0
    for doc in documents:
        any_missing = False
        all_ok = True
        for p, t in paths:
            verdict = _check_path(doc, p, t)
            s = stats[p]
            if verdict == _PRESENT:
                s.present += 1
            elif verdict == _MISSING:
                s.missing += 1
                any_missing = True
                all_ok = False
            elif verdict == _NULL:
                s.null += 1
                all_ok = False
            elif verdict == _WRONG_TYPE:
                s.wrong_type += 1
                all_ok = False
        if all_ok:
            docs_all_ok += 1
        if any_missing:
            docs_any_missing += 1
    return CoverageReport(
        documents_total=len(documents),
        documents_all_required_present=docs_all_ok,
        documents_with_at_least_one_missing=docs_any_missing,
        fields=[stats[p] for p, _ in paths],
    )


def report_json(schema: dict, documents: list[Any]) -> str:
    return json.dumps(report(schema, documents).to_dict(), indent=2, sort_keys=False)

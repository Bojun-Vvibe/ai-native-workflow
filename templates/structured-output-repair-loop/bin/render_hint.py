#!/usr/bin/env python3
"""Render a validator error as a structured repair-hint block.

Used by repair_loop.py to construct the user-turn for attempt N>1.
Stdlib only.
"""
from __future__ import annotations

import json
import sys
from typing import Any


HINT_TEMPLATE = """=== REPAIR REQUIRED ===
Previous attempt failed validation:
  path:     {pointer}
  error:    {expected}
  got:      {got}
  fix:      {fix}

Reproduce ALL fields from the previous attempt EXCEPT the one
above. Do not change other fields. Do not add explanatory prose.
=== END REPAIR ==="""


def _suggest_fix(err: dict[str, Any]) -> str:
    cls = err.get("error_class", "")
    ptr = err.get("json_pointer", "/")
    expected = err.get("expected", "")
    if cls == "EnumViolation":
        return f"Replace the value at {ptr} with one of: {expected}."
    if cls == "MissingField":
        return f"Add the required field {ptr} (expected: {expected})."
    if cls == "ExtraField":
        return f"Remove the disallowed field {ptr}."
    if cls == "TypeMismatch":
        return f"Change the value at {ptr} to type {expected}."
    if cls == "JSONDecodeError":
        return ("Output must be a single JSON object with no surrounding "
                "prose, code fences, or commentary.")
    return f"Replace the value at {ptr} so it matches: {expected}."


def render_hint(err: dict[str, Any]) -> str:
    return HINT_TEMPLATE.format(
        pointer=err.get("json_pointer", "/"),
        expected=err.get("expected", ""),
        got=json.dumps(err.get("got", None)),
        fix=_suggest_fix(err),
    )


def main(argv: list[str]) -> int:
    raw = sys.stdin.read() if len(argv) == 1 else open(argv[1]).read()
    err = json.loads(raw)
    print(render_hint(err))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

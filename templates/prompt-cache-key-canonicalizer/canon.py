#!/usr/bin/env python3
"""Prompt-cache-key canonicalizer.

Stdlib only. Produces stable SHA-256 cache keys for prompt-call
descriptors. See SPEC.md.

CLI:
    python canon.py < descriptor.json
        prints {"canonical": "...", "key": "..."}
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from typing import Any


def _canon_float(x: float) -> float:
    if math.isnan(x) or math.isinf(x):
        raise ValueError(f"non-finite float not cacheable: {x}")
    # Round-trip through repr to get the shortest stable form.
    return float(format(x, ".17g"))


def _canon_value(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return _canon_float(v)
    if isinstance(v, int):
        return v
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, list):
        return [_canon_value(item) for item in v]
    if isinstance(v, dict):
        return {k: _canon_value(v[k]) for k in sorted(v.keys())}
    raise TypeError(f"unsupported type: {type(v).__name__}")


def _hash_context(context: Any) -> str:
    if context is None:
        return hashlib.sha256(b"null").hexdigest()
    canon = json.dumps(_canon_value(context), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def canonicalize(desc: dict) -> tuple[str, str]:
    if "model" not in desc or "prompt" not in desc or "temperature" not in desc:
        raise ValueError("descriptor requires model, prompt, temperature")

    out: dict[str, Any] = {}
    out["context_hash"] = _hash_context(desc.get("context"))
    out["model"] = str(desc["model"])
    out["prompt"] = _canon_value(desc["prompt"])
    out["temperature"] = round(float(desc["temperature"]), 4)

    tools = desc.get("tools")
    if tools is not None:
        canon_tools = [_canon_value(t) for t in tools]
        # Sort tools by name (commutative).
        canon_tools.sort(key=lambda t: t.get("name", "") if isinstance(t, dict) else "")
        out["tools"] = canon_tools

    canonical = json.dumps(out, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return canonical, key


def main(argv: list[str]) -> int:
    desc = json.load(sys.stdin)
    canonical, key = canonicalize(desc)
    print(json.dumps({"canonical": canonical, "key": key}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

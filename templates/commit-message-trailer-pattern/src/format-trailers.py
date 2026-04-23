#!/usr/bin/env python3
"""Format a trailer block from a usage record.

Input: a JSON dict on stdin with keys matching the canonical trailer
keys (lowercase, underscores allowed for input convenience). Output
on stdout: a trailer block ready to append to a commit message.

Always emits a leading blank line — append directly after the body.
"""
from __future__ import annotations

import json
import sys


ALLOWED = [
    "Co-Authored-By",
    "Mission-Id",
    "Model",
    "Tokens-In",
    "Tokens-Out",
    "Cache-Hit-Rate",
    "Signed-off-by",
]


def _normalize_key(k: str) -> str:
    return "-".join(p.capitalize() if p not in {"Id"} else "Id" for p in k.replace("_", "-").split("-"))


def format_trailers(record: dict) -> str:
    out_lines = [""]
    for ckey in ALLOWED:
        # Find an input key that normalizes to ckey.
        for ikey, val in record.items():
            if _normalize_key(ikey) == ckey:
                if isinstance(val, list):
                    for v in val:
                        out_lines.append(f"{ckey}: {v}")
                else:
                    if ckey == "Cache-Hit-Rate" and isinstance(val, float):
                        val = f"{val:.3f}"
                    out_lines.append(f"{ckey}: {val}")
    return "\n".join(out_lines) + "\n"


if __name__ == "__main__":
    record = json.load(sys.stdin)
    sys.stdout.write(format_trailers(record))

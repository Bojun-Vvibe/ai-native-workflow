"""Worked example for agent-tool-call-argument-key-stability-checker."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from validator import validate  # noqa: E402


CALLS = [
    {"tool": "search", "args": {"query": "alpha", "limit": 10}},
    {"tool": "search", "args": {"query": "beta", "limit": 10}},
    {"tool": "search", "args": {"q": "gamma", "limit": 10}},
    {"tool": "search", "args": {"query": "delta", "limit": "10"}},
    {"tool": "search",
     "args": {"limit": 10, "query": "epsilon", "filter": "recent"}},
    {"tool": "fetch", "args": {"url": "https://example.test/a"}},
    {"tool": "fetch", "args": {"url": "https://example.test/b"}},
]


def main() -> int:
    findings = validate(CALLS)
    print(json.dumps([f.__dict__ for f in findings], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
agent-tool-call-argument-key-typo-detector

Reads a JSON document on stdin describing a tool's expected argument schema
and a list of attempted tool calls, then flags argument keys that look like
typos of expected keys (close-but-not-equal). This catches the common LLM
failure where the model invents a near-miss key like "file_path" instead of
"path", "queryString" instead of "query", or "max_token" instead of
"max_tokens".

Input shape:
{
  "tools": {
    "<tool_name>": {
      "expected": ["key1", "key2", ...],
      "required": ["key1"]            # optional subset
    }
  },
  "calls": [
    {"tool": "<tool_name>", "args": {"key": ...}},
    ...
  ]
}

Output: JSON report on stdout. Exit 0 if no suspect keys, exit 2 otherwise.

Detection:
  - Unknown key whose normalized form (lowercased, underscores/dashes/dots
    stripped) matches an expected key  -> normalization typo
  - Unknown key with edit distance <= max(1, len(key)//4) to an expected key
    -> edit-distance typo
  - Missing required key when a near-miss unknown key is present  -> linked
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List, Optional


def normalize(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def best_match(key: str, expected: List[str]) -> Optional[Dict]:
    nkey = normalize(key)
    # 1. exact normalization hit
    for e in expected:
        if normalize(e) == nkey and e != key:
            return {"suggested": e, "reason": "normalization", "distance": 0}
    # 2. substring containment (e.g., 'file_path' contains 'path',
    #    'queryString' contains 'query'); only when the expected key is
    #    a meaningful chunk (>=3 chars) of the offered key
    for e in expected:
        ne = normalize(e)
        if len(ne) >= 3 and ne in nkey and ne != nkey:
            return {"suggested": e, "reason": "substring", "distance": len(nkey) - len(ne)}
    # 3. edit distance
    threshold = max(1, len(key) // 4)
    best = None
    for e in expected:
        if e == key:
            return None  # exact match
        d = levenshtein(key.lower(), e.lower())
        if d <= threshold and (best is None or d < best["distance"]):
            best = {"suggested": e, "reason": "edit-distance", "distance": d}
    return best


def analyze_call(call: Dict, tools: Dict) -> Dict:
    tool_name = call.get("tool")
    args = call.get("args") or {}
    spec = tools.get(tool_name)
    if not spec:
        return {"tool": tool_name, "error": "unknown-tool", "args": list(args.keys())}
    expected = spec.get("expected", [])
    required = spec.get("required", [])
    suspects = []
    for k in args.keys():
        if k in expected:
            continue
        m = best_match(k, expected)
        if m:
            suspects.append({"key": k, **m})
        else:
            suspects.append({"key": k, "suggested": None, "reason": "unknown", "distance": None})
    missing_required = [r for r in required if r not in args]
    # Cross-link: if a required key is missing and a suspect points at it,
    # mark the suspect as 'likely-typo-of-required'.
    for s in suspects:
        if s.get("suggested") in missing_required:
            s["likely_typo_of_required"] = True
    return {
        "tool": tool_name,
        "suspects": suspects,
        "missing_required": missing_required,
    }


def main() -> int:
    raw = sys.stdin.read()
    doc = json.loads(raw)
    tools = doc.get("tools", {})
    calls = doc.get("calls", [])
    findings = [analyze_call(c, tools) for c in calls]
    bad = [
        f for f in findings
        if f.get("error") or any(s.get("suggested") or s.get("reason") == "unknown" for s in f.get("suspects", []))
        or f.get("missing_required")
    ]
    report = {
        "calls_analyzed": len(findings),
        "calls_with_issues": len(bad),
        "findings": findings,
    }
    print(json.dumps(report, indent=2))
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())

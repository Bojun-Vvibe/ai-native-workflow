"""
agent-tool-call-argument-key-stability-checker

Audits a series of tool calls (e.g. captured from an agent trace)
for *argument-key drift* — the agent calls the same tool name with a
slightly different set of argument keys across calls, even when the
intent is identical. This is a leading indicator of:

- prompt regressions (the schema example in the system prompt was
  paraphrased and the model started omitting an optional key);
- tool schema drift (the tool added a key, the model picked it up
  on call 4 but not call 5);
- silent fallback paths in tool routing (the tool tolerates
  `query` *or* `q` and the model alternates).

Input: JSONL on stdin, one tool call per line. Each line has
`tool` (str) and `args` (object). Order matters; the first call
defines the *baseline* key set per tool.

Five finding classes, all keyed by `(tool, call_index)`:

- `key_added_after_baseline` — call N introduces a key not present
  in call 0 for the same tool.
- `key_dropped_after_baseline` — call N is missing a key that was
  present in call 0.
- `key_alias_pair` — across the whole trace, two calls of the same
  tool use disjoint key sets that are 1-character-different
  (Levenshtein ≤1) — likely typo aliases (`q` vs `query`,
  `path` vs `paths`).
- `value_type_changed` — same tool, same key, but the JSON type of
  the value changed across calls (`str` → `list`, `int` → `str`).
  Reports the call_index where the type first changes.
- `key_order_unstable` — the JSON key *order* across calls of the
  same tool varies. (Not strictly semantic, but a strong signal
  the model is reconstructing the argument object instead of
  templating it — correlates with quality drops.)

Pure stdlib. Deterministic ordering: `(tool, call_index, kind, key)`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Finding:
    tool: str
    call_index: int
    kind: str
    key: str
    detail: str


def _levenshtein_le_1(a: str, b: str) -> bool:
    if a == b:
        return False
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = sum(1 for x, y in zip(a, b) if x != y)
        return diffs == 1
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = j = 0
    skipped = False
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        else:
            if skipped:
                return False
            skipped = True
            j += 1
    return True


def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def validate(calls: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    by_tool: dict[str, list[tuple[int, dict]]] = {}

    for idx, c in enumerate(calls):
        tool = c.get("tool")
        args = c.get("args", {}) or {}
        if not isinstance(tool, str) or not isinstance(args, dict):
            continue
        by_tool.setdefault(tool, []).append((idx, args))

    for tool, sequence in by_tool.items():
        if not sequence:
            continue
        baseline_idx, baseline = sequence[0]
        baseline_keys = set(baseline.keys())
        baseline_order = list(baseline.keys())

        type_first_seen: dict[str, tuple[int, str]] = {
            k: (baseline_idx, _type_name(v)) for k, v in baseline.items()
        }

        for call_idx, args in sequence[1:]:
            keys = set(args.keys())
            for added in sorted(keys - baseline_keys):
                findings.append(Finding(
                    tool=tool, call_index=call_idx,
                    kind="key_added_after_baseline",
                    key=added,
                    detail=f"baseline_call={baseline_idx}",
                ))
            for dropped in sorted(baseline_keys - keys):
                findings.append(Finding(
                    tool=tool, call_index=call_idx,
                    kind="key_dropped_after_baseline",
                    key=dropped,
                    detail=f"baseline_call={baseline_idx}",
                ))
            for k, v in args.items():
                t = _type_name(v)
                if k in type_first_seen and type_first_seen[k][1] != t:
                    prev_idx, prev_t = type_first_seen[k]
                    findings.append(Finding(
                        tool=tool, call_index=call_idx,
                        kind="value_type_changed",
                        key=k,
                        detail=f"{prev_t}@call{prev_idx}->{t}",
                    ))
                    type_first_seen[k] = (call_idx, t)
                elif k not in type_first_seen:
                    type_first_seen[k] = (call_idx, t)

            order = list(args.keys())
            common = [k for k in order if k in baseline_order]
            common_baseline = [k for k in baseline_order if k in keys]
            if common != common_baseline and common:
                findings.append(Finding(
                    tool=tool, call_index=call_idx,
                    kind="key_order_unstable",
                    key=",".join(order),
                    detail=f"baseline_order={','.join(baseline_order)}",
                ))

        seen_keys: set[str] = set()
        for _, args in sequence:
            seen_keys.update(args.keys())
        seen_sorted = sorted(seen_keys)
        _COMMON_ABBREV = {
            ("q", "query"), ("p", "path"), ("u", "url"), ("k", "key"),
            ("v", "value"), ("n", "name"), ("id", "identifier"),
            ("msg", "message"), ("max", "maximum"), ("min", "minimum"),
            ("num", "number"), ("dir", "directory"), ("ts", "timestamp"),
        }
        for i, a in enumerate(seen_sorted):
            for b in seen_sorted[i + 1:]:
                pair = (a, b)
                if _levenshtein_le_1(a, b):
                    findings.append(Finding(
                        tool=tool, call_index=-1,
                        kind="key_alias_pair",
                        key=f"{a}|{b}",
                        detail="levenshtein<=1",
                    ))
                elif pair in _COMMON_ABBREV:
                    findings.append(Finding(
                        tool=tool, call_index=-1,
                        kind="key_alias_pair",
                        key=f"{a}|{b}",
                        detail="known_abbreviation",
                    ))

    findings.sort(key=lambda f: (f.tool, f.call_index, f.kind, f.key))
    return findings


def main(argv: list[str]) -> int:
    if len(argv) == 2:
        with open(argv[1], "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    elif len(argv) == 1:
        lines = sys.stdin.readlines()
    else:
        print("usage: validator.py [<file.jsonl>]", file=sys.stderr)
        return 2
    calls = [json.loads(ln) for ln in lines if ln.strip()]
    findings = validate(calls)
    print(json.dumps([asdict(f) for f in findings], indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

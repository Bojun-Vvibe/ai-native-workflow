"""llm-output-json-duplicate-key-detector — checker + worked demo.

Pure-stdlib detector for *duplicate keys at the same object scope* in
JSON emitted by an LLM. RFC 8259 says member names "SHOULD be unique"
and that the behaviour is undefined when they are not — every popular
consumer made a different choice:

  * Python's json.loads silently keeps the LAST value
  * JavaScript's JSON.parse silently keeps the LAST value
  * Go's encoding/json silently keeps the LAST value... but
    json.RawMessage round-trips both
  * Ruby's JSON.parse silently keeps the FIRST in some versions, LAST
    in others
  * jq prints both with `--seq` and merges to last otherwise

The model never sees the disagreement. The pipeline ingests the doc,
each consumer reads a *different* value for the same key, and the
downstream state diverges by service. This detector flags it before
ingestion so the model can be asked to regenerate.

The checker walks the JSON token stream by hand instead of using
json.loads because json.loads collapses duplicates before the caller
can see them. We do not validate full JSON grammar — a broken JSON
file is the trailing-comma detector's job; we only flag duplicate
member names inside otherwise-balanced object braces.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class Finding:
    kind: str           # "duplicate_key"
    key: str            # the duplicated member name
    line_no: int        # 1-indexed line of the *second* (or later) occurrence
    col_no: int         # 1-indexed column of the duplicated key's opening quote
    first_line_no: int  # where the same key appeared first in the same scope
    detail: str


@dataclass
class JsonDupKeyReport:
    ok: bool
    scopes_checked: int
    keys_checked: int
    findings: List[Finding] = field(default_factory=list)


def _scan_string(src: str, i: int) -> Tuple[str, int]:
    """Scan a JSON string starting at src[i] == '"'. Return (value, end_index_exclusive)."""
    assert src[i] == '"'
    j = i + 1
    out_chars: List[str] = []
    while j < len(src):
        c = src[j]
        if c == "\\":
            if j + 1 >= len(src):
                raise ValueError("trailing backslash")
            esc = src[j + 1]
            simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b",
                      "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
            if esc in simple:
                out_chars.append(simple[esc])
                j += 2
            elif esc == "u":
                if j + 6 > len(src):
                    raise ValueError("short \\u escape")
                out_chars.append(chr(int(src[j + 2:j + 6], 16)))
                j += 6
            else:
                raise ValueError(f"bad escape \\{esc}")
        elif c == '"':
            return "".join(out_chars), j + 1
        else:
            out_chars.append(c)
            j += 1
    raise ValueError("unterminated string")


def _line_col(src: str, idx: int) -> Tuple[int, int]:
    line = src.count("\n", 0, idx) + 1
    last_nl = src.rfind("\n", 0, idx)
    col = idx - last_nl if last_nl >= 0 else idx + 1
    return line, col


def detect(src: str) -> JsonDupKeyReport:
    """Walk src, track per-object key sets, emit duplicate findings."""
    findings: List[Finding] = []
    # Stack of dicts: key -> first_occurrence_line
    scope_stack: List[dict] = []
    scopes_checked = 0
    keys_checked = 0

    i = 0
    expect_key = False  # True after `{` or `,` inside an object
    in_object_stack: List[bool] = []  # True for object scopes, False for arrays

    while i < len(src):
        c = src[i]
        if c.isspace():
            i += 1
            continue
        # Skip strings that are *values* (not keys) cleanly
        if c == "{":
            scope_stack.append({})
            in_object_stack.append(True)
            scopes_checked += 1
            expect_key = True
            i += 1
            continue
        if c == "}":
            if not in_object_stack or not in_object_stack[-1]:
                # Mismatched — out of scope for this detector; bail gracefully.
                break
            scope_stack.pop()
            in_object_stack.pop()
            expect_key = False
            i += 1
            continue
        if c == "[":
            in_object_stack.append(False)
            expect_key = False
            i += 1
            continue
        if c == "]":
            if not in_object_stack or in_object_stack[-1]:
                break
            in_object_stack.pop()
            expect_key = False
            i += 1
            continue
        if c == ",":
            expect_key = bool(in_object_stack and in_object_stack[-1])
            i += 1
            continue
        if c == ":":
            expect_key = False
            i += 1
            continue
        if c == '"':
            try:
                value, end = _scan_string(src, i)
            except ValueError:
                break
            if expect_key and in_object_stack and in_object_stack[-1]:
                keys_checked += 1
                scope = scope_stack[-1]
                line, col = _line_col(src, i)
                if value in scope:
                    findings.append(Finding(
                        kind="duplicate_key",
                        key=value,
                        line_no=line,
                        col_no=col,
                        first_line_no=scope[value],
                        detail=(f"key {value!r} reappears at line {line}; "
                                f"first seen at line {scope[value]}"),
                    ))
                else:
                    scope[value] = line
                expect_key = False
            i = end
            continue
        # numbers, true, false, null — skip until structural char
        i += 1

    findings.sort(key=lambda f: (f.line_no, f.col_no, f.key))
    return JsonDupKeyReport(
        ok=not findings,
        scopes_checked=scopes_checked,
        keys_checked=keys_checked,
        findings=findings,
    )


# --- worked-example cases -------------------------------------------------

_CASES: List[Tuple[str, str]] = [
    ("01_clean_flat", '{"id": 1, "name": "alice", "active": true}'),
    ("02_clean_nested", json.dumps({
        "user": {"id": 1, "name": "alice"},
        "roles": ["admin", "editor"],
    }, indent=2)),
    ("03_dup_top_level",
     '{\n  "id": 1,\n  "name": "alice",\n  "id": 2\n}'),
    ("04_dup_in_nested",
     '{\n  "user": {\n    "name": "alice",\n    "name": "bob"\n  }\n}'),
    ("05_dup_inside_array_of_objects",
     '[\n  {"k": 1, "k": 2},\n  {"k": 3}\n]'),
    ("06_same_key_diff_scopes_is_clean",
     '{"a": {"x": 1}, "b": {"x": 2}}'),
    ("07_three_way_dup",
     '{"flag": true, "flag": false, "flag": null}'),
]


def _to_jsonable(rep: JsonDupKeyReport) -> dict:
    d = asdict(rep)
    return d


def main() -> int:
    print("# llm-output-json-duplicate-key-detector — worked example\n")
    any_findings = False
    for name, src in _CASES:
        rep = detect(src)
        if rep.findings:
            any_findings = True
        print(f"## case {name}")
        print(f"input_bytes: {len(src)} scopes_checked: {rep.scopes_checked} "
              f"keys_checked: {rep.keys_checked}")
        print(json.dumps(_to_jsonable(rep), indent=2, sort_keys=True))
        print()
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main())

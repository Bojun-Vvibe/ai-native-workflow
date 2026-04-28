#!/usr/bin/env python3
"""llm-output-jsonl-mixed-schema-detector.

Pure-stdlib, code-fence-aware detector for JSONL (newline-delimited
JSON) blocks emitted by an LLM where the records do not share a
single object schema (i.e., the *set of top-level keys* drifts
across lines).

Why it matters
--------------
JSONL is a streaming format. Downstream consumers (Spark, DuckDB
`read_json_auto`, BigQuery, pandas `read_json(lines=True)`) infer a
single schema from the first batch of records and then reject —
or, worse, silently null out — fields that show up later. LLMs that
are asked for "20 sample rows" routinely emit:

    {"id": 1, "name": "alice", "email": "a@x"}
    {"id": 2, "name": "bob"}                              <-- no email
    {"id": 3, "full_name": "carol", "email": "c@x"}       <-- key renamed

This detector reads each non-blank line, parses it as JSON, computes
the set of top-level keys, and reports any line whose key-set differs
from the *baseline* (the key-set of the first valid object record).

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {jsonl, ndjson, json-lines,
jsonlines}, and runs the schema-drift check on each.

Output: one finding per line on stdout, of the form::

    block=<N> line=<L> kind=<k> [extra=...] [missing=...]

Trailing summary `total_findings=<N> blocks_checked=<M>` is printed
to stderr. Exit code 0 if no findings, 1 if any.

What it flags
-------------
    schema_drift        Top-level key-set differs from baseline (the
                        first valid object record). `extra=` lists
                        keys present in this row but not the
                        baseline; `missing=` lists baseline keys
                        absent here.
    not_object          Line parsed as JSON but is not an object
                        (e.g. a bare array or scalar). JSONL records
                        are conventionally objects.
    invalid_json        Line could not be parsed as JSON at all.

Out of scope (deliberately): nested-schema comparison, type
comparison of values, key ordering, key-case mismatch beyond the
exact-string set difference. This is a *first-line-defense* sniff
test, not a JSON Schema validator.
"""
from __future__ import annotations

import json
import sys
from typing import List, Tuple


_JSONL_TAGS = {"jsonl", "ndjson", "json-lines", "jsonlines"}


def extract_jsonl_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for each JSONL block.

    start_line_no is the 1-indexed line of the first line *inside*
    the fence.
    """
    blocks: List[Tuple[int, int, str]] = []
    lines = src.splitlines()
    i = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_tag = ""
    body: List[str] = []
    body_start = 0
    block_idx = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = 0
                while run < len(stripped) and stripped[run] == ch:
                    run += 1
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    body_start = i + 2
                    i += 1
                    continue
            i += 1
            continue
        s = stripped.rstrip()
        if s and set(s) == {fence_char} and len(s) >= fence_len:
            if fence_tag in _JSONL_TAGS:
                block_idx += 1
                blocks.append((block_idx, body_start, "\n".join(body)))
            in_fence = False
            fence_tag = ""
            i += 1
            continue
        body.append(line)
        i += 1
    if in_fence and fence_tag in _JSONL_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))
    return blocks


def detect_in_block(body: str) -> List[Tuple[int, str, dict]]:
    """Return list of (line_no, kind, extras) findings within one JSONL block.

    line_no is 1-indexed within the block. extras is a dict that may
    contain `extra` (sorted list of keys) and `missing` (sorted list
    of keys) for `schema_drift`, or be empty.
    """
    findings: List[Tuple[int, str, dict]] = []
    baseline: set | None = None
    for lineno, raw in enumerate(body.split("\n"), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            findings.append((lineno, "invalid_json", {}))
            continue
        if not isinstance(parsed, dict):
            findings.append((lineno, "not_object", {}))
            continue
        keys = set(parsed.keys())
        if baseline is None:
            baseline = keys
            continue
        if keys != baseline:
            extra = sorted(keys - baseline)
            missing = sorted(baseline - keys)
            findings.append((lineno, "schema_drift",
                             {"extra": extra, "missing": missing}))
    return findings


def _format_extras(extras: dict) -> str:
    parts = []
    if "extra" in extras:
        parts.append(f"extra={','.join(extras['extra']) or '-'}")
    if "missing" in extras:
        parts.append(f"missing={','.join(extras['missing']) or '-'}")
    return (" " + " ".join(parts)) if parts else ""


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()
    blocks = extract_jsonl_blocks(src)
    total = 0
    for block_idx, _start, body in blocks:
        for lineno, kind, extras in detect_in_block(body):
            total += 1
            print(f"block={block_idx} line={lineno} kind={kind}"
                  f"{_format_extras(extras)}")
    print(f"total_findings={total} blocks_checked={len(blocks)}",
          file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

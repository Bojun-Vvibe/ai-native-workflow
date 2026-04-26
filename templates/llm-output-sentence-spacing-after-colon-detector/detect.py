#!/usr/bin/env python3
"""
llm-output-sentence-spacing-after-colon-detector

Detect inconsistent or pathological spacing after a `:` colon in
an LLM Markdown / prose output blob.

Why this exists:
    LLM outputs often mix three different colon-spacing conventions
    in the same document:
      - "label: value"  (one space — the standard prose form)
      - "label:value"   (zero space — leaks from JSON/code or from
                         a stop-token cut)
      - "label:  value" (two-or-more spaces — leaks from a fixed-
                         width / aligned-table source)
    Each convention is fine on its own; mixing them in the same
    blob is a tell that the model concatenated chunks from
    different sources mid-generation.

    Colons inside URLs (`https://`), times (`12:30`), code spans
    (between backticks), and code fences are excluded.

Behavior:
    - Lines inside fenced code blocks (``` or ~~~) are skipped.
    - Inside backtick-delimited inline code spans on a prose
      line, the colon is also ignored.
    - Colons immediately followed by `//` are treated as URL
      schemes and skipped (`https://`, `git://`).
    - A colon flanked on BOTH sides by ASCII digits (`12:30`,
      `1:1 ratio`) is treated as a time/ratio and skipped.
    - A colon at end-of-line is treated as a list/heading lead-in
      and skipped (no spacing to check).
    - For every remaining colon, we record the post-colon
      whitespace run length: 0, 1, or 2+. Tabs count as a 2+ run.

Finding kinds:
    - mixed_colon_spacing — the document uses MORE THAN ONE
      convention (any two of {0-space, 1-space, 2+-space} both
      appear). Reported once, scope=blob, with the inventory.
    - excess_space_after_colon — a run of 2+ spaces (or any tab)
      after a colon. Reported per occurrence with line/col/run.
    - zero_space_after_colon_in_one_space_blob — a 0-space colon
      in a blob whose majority is 1-space. Per occurrence.

Exit code:
    0 if no findings, 1 if any finding fired.

Usage:
    python3 detect.py < input.md
    python3 detect.py path/to/file.md
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from typing import List, Tuple

FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")


def _strip_inline_code(line: str) -> str:
    """Replace inline-code spans with same-length runs of '\x00'.

    Preserves columns so reported (line, col) stays accurate, but
    ensures colons inside `` `code` `` are not counted.
    """
    out = list(line)
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            # find the run length
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = j - i
            # find matching closer of the same length
            k = j
            while k < n:
                if line[k] == "`":
                    m = k
                    while m < n and line[m] == "`":
                        m += 1
                    if m - k == run:
                        # close
                        for p in range(i, m):
                            out[p] = "\x00"
                        i = m
                        break
                    else:
                        k = m
                else:
                    k += 1
            else:
                # no closer — leave as-is (the backtick-balance
                # detector handles that bug class)
                i = j
        else:
            i += 1
    return "".join(out)


def _is_url_scheme(line: str, idx: int) -> bool:
    return line[idx + 1 : idx + 3] == "//"


def _is_digit_flanked(line: str, idx: int) -> bool:
    if idx == 0 or idx == len(line) - 1:
        return False
    return line[idx - 1].isdigit() and line[idx + 1].isdigit()


def _post_colon_run(line: str, idx: int) -> Tuple[int, bool]:
    """Return (run_length, has_tab) for whitespace after line[idx]==':'."""
    j = idx + 1
    has_tab = False
    while j < len(line) and line[j] in (" ", "\t"):
        if line[j] == "\t":
            has_tab = True
        j += 1
    return (j - idx - 1, has_tab)


def detect(text: str) -> List[dict]:
    findings: List[dict] = []
    in_fence = False
    fence_marker = ""

    occurrences: List[dict] = []  # per-colon records
    for lineno, raw in enumerate(text.splitlines(), start=1):
        fence_match = FENCE_RE.match(raw)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker[0] * 3
            else:
                if marker[0] * 3 == fence_marker:
                    in_fence = False
                    fence_marker = ""
            continue
        if in_fence:
            continue

        scrubbed = _strip_inline_code(raw)
        for idx, ch in enumerate(scrubbed):
            if ch != ":":
                continue
            # end of line — list/heading lead-in
            if idx == len(scrubbed) - 1:
                continue
            # url scheme
            if _is_url_scheme(scrubbed, idx):
                continue
            # time / ratio
            if _is_digit_flanked(scrubbed, idx):
                continue
            # post-colon char must be whitespace (else it's
            # `label:value` zero-space form — we DO record that)
            nxt = scrubbed[idx + 1]
            if nxt not in (" ", "\t") and not nxt.isspace():
                # zero-space, but only if next is a "value" char
                # (letter/digit/quote/bracket). Skip for symbols
                # like `::`, `:)`, `:-)` which aren't prose colons.
                if not (nxt.isalnum() or nxt in '"\'([{'):
                    continue
                occurrences.append({
                    "line": lineno,
                    "col": idx + 1,
                    "run": 0,
                    "has_tab": False,
                })
                continue
            run, has_tab = _post_colon_run(scrubbed, idx)
            occurrences.append({
                "line": lineno,
                "col": idx + 1,
                "run": run,
                "has_tab": has_tab,
            })

    if not occurrences:
        return []

    # bucket: 0, 1, 2+ (tab counts as 2+)
    def bucket(o):
        if o["has_tab"]:
            return "2+"
        if o["run"] == 0:
            return "0"
        if o["run"] == 1:
            return "1"
        return "2+"

    counts = Counter(bucket(o) for o in occurrences)
    distinct = sum(1 for k in ("0", "1", "2+") if counts.get(k, 0) > 0)

    if distinct > 1:
        findings.append({
            "kind": "mixed_colon_spacing",
            "scope": "blob",
            "inventory": {
                "zero_space": counts.get("0", 0),
                "one_space": counts.get("1", 0),
                "two_or_more_space": counts.get("2+", 0),
            },
        })

    # majority for the in-minority finding
    majority = counts.most_common(1)[0][0]

    for o in occurrences:
        if o["has_tab"] or o["run"] >= 2:
            findings.append({
                "kind": "excess_space_after_colon",
                "line": o["line"],
                "col": o["col"],
                "run_length": o["run"],
                "tab": o["has_tab"],
            })
        elif o["run"] == 0 and majority == "1":
            findings.append({
                "kind": "zero_space_after_colon_in_one_space_blob",
                "line": o["line"],
                "col": o["col"],
            })

    return findings


def format_report(findings: List[dict]) -> str:
    if not findings:
        return "OK: no colon-spacing issues.\n"
    lines = [f"FAIL: {len(findings)} finding(s)."]
    for f in findings:
        if f["kind"] == "mixed_colon_spacing":
            inv = f["inventory"]
            lines.append(
                f"  blob: mixed_colon_spacing "
                f"zero={inv['zero_space']} "
                f"one={inv['one_space']} "
                f"two_or_more={inv['two_or_more_space']}"
            )
        elif f["kind"] == "excess_space_after_colon":
            tag = "tab" if f["tab"] else f"run={f['run_length']}"
            lines.append(
                f"  L{f['line']} col {f['col']}: excess_space_after_colon ({tag})"
            )
        else:
            lines.append(
                f"  L{f['line']} col {f['col']}: zero_space_after_colon_in_one_space_blob"
            )
    return "\n".join(lines) + "\n"


def main(argv: List[str]) -> int:
    if len(argv) > 1:
        with open(argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()
    findings = detect(text)
    sys.stdout.write(format_report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

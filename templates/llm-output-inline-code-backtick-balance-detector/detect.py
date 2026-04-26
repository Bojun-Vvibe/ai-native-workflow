#!/usr/bin/env python3
"""
llm-output-inline-code-backtick-balance-detector

Detect unbalanced inline-code backticks in an LLM Markdown / prose
output blob, while ignoring backticks that belong to a fenced code
block opener/closer (``` or ~~~ at start of line).

Why this exists:
    A model that emits `foo and forgets the closer turns the rest of
    the paragraph into one giant inline-code span when rendered. It
    is invisible to the model itself (no syntax error) but loud to
    every human reader. The bug class is "odd count of inline
    backticks on a line that has no fence opener/closer on it".

Behavior:
    - Lines that are themselves a fenced-code delimiter (``` or ~~~,
      optionally followed by an info string) are skipped entirely.
    - Inside a fenced block, ALL lines are skipped — backticks
      inside a code fence are content, not markup.
    - For each remaining (prose) line, we count runs of backticks.
      A "run" is one or more consecutive backticks; `code` opens
      with a 1-run and closes with a matching 1-run, ``has `tick``
      opens with 2-run and closes with 2-run. We require runs to
      come in pairs of equal length per line. Any line whose
      backtick runs cannot be perfectly paired by length is flagged.

Finding kinds:
    - unpaired_inline_backtick — line has an inline-code opener
      with no closer of equal run-length on the same line. Common
      cause: model dropped the trailing backtick.
    - odd_total_backtick_run_count — line has an odd number of
      backtick runs total (not just unpaired by length). This is a
      stronger signal — even if every length pairs, an odd count
      means at least one run is dangling.

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
BACKTICK_RUN_RE = re.compile(r"`+")


def find_backtick_runs(line: str) -> List[Tuple[int, int]]:
    """Return list of (col, run_length) for every backtick run on the line."""
    return [(m.start(), len(m.group(0))) for m in BACKTICK_RUN_RE.finditer(line)]


def detect(text: str) -> List[dict]:
    findings: List[dict] = []
    in_fence = False
    fence_marker = ""

    for lineno, raw in enumerate(text.splitlines(), start=1):
        fence_match = FENCE_RE.match(raw)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker[0] * 3  # normalize to 3-char family
            else:
                # only close on same marker family
                if marker[0] * 3 == fence_marker:
                    in_fence = False
                    fence_marker = ""
            continue

        if in_fence:
            continue

        runs = find_backtick_runs(raw)
        if not runs:
            continue

        # odd total run count is unrecoverable
        if len(runs) % 2 == 1:
            findings.append({
                "kind": "odd_total_backtick_run_count",
                "line": lineno,
                "run_count": len(runs),
                "runs": [{"col": c + 1, "len": L} for c, L in runs],
            })
            continue

        # pair runs by length; every length must appear an even count
        length_counts = Counter(L for _, L in runs)
        unpaired_lengths = {L: n for L, n in length_counts.items() if n % 2 == 1}
        if unpaired_lengths:
            findings.append({
                "kind": "unpaired_inline_backtick",
                "line": lineno,
                "run_count": len(runs),
                "unpaired_run_lengths": dict(unpaired_lengths),
                "runs": [{"col": c + 1, "len": L} for c, L in runs],
            })

    return findings


def format_report(findings: List[dict]) -> str:
    if not findings:
        return "OK: no inline-backtick balance issues.\n"
    lines = [f"FAIL: {len(findings)} finding(s)."]
    for f in findings:
        if f["kind"] == "odd_total_backtick_run_count":
            cols = ", ".join(f"col {r['col']} (len {r['len']})" for r in f["runs"])
            lines.append(
                f"  L{f['line']}: odd_total_backtick_run_count "
                f"run_count={f['run_count']} runs=[{cols}]"
            )
        else:
            cols = ", ".join(f"col {r['col']} (len {r['len']})" for r in f["runs"])
            lines.append(
                f"  L{f['line']}: unpaired_inline_backtick "
                f"unpaired_lengths={f['unpaired_run_lengths']} runs=[{cols}]"
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

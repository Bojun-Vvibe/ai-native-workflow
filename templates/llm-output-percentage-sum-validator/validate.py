#!/usr/bin/env python3
"""
llm-output-percentage-sum-validator

Reads LLM output text from stdin, finds groups of percentages that look like
they should sum to ~100% (e.g., breakdowns, allocations, distributions), and
flags groups whose sum drifts beyond a tolerance.

Heuristics for grouping:
  - Bullet/numbered lists where every item contains exactly one "NN%" or "NN.N%"
    token are treated as a group.
  - Inline "A: 30%, B: 40%, C: 25%" style sequences (>=3 percentages on one
    line, separated by commas/semicolons) are a group.
  - Markdown tables where one column is entirely percentages: that column is
    a group.

Output: JSON report on stdout, exit 0 if all groups OK, exit 2 if any group
drifts beyond tolerance.
"""
from __future__ import annotations

import json
import re
import sys
from typing import List, Tuple

PCT_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d+)?)\s*%")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TOLERANCE = 1.0  # percentage points


def find_bullet_groups(lines: List[str]) -> List[Tuple[str, List[float], List[int]]]:
    groups = []
    i = 0
    while i < len(lines):
        if BULLET_RE.match(lines[i]) and len(PCT_RE.findall(lines[i])) == 1:
            start = i
            vals = []
            line_nos = []
            while i < len(lines) and BULLET_RE.match(lines[i]) and len(PCT_RE.findall(lines[i])) == 1:
                vals.append(float(PCT_RE.findall(lines[i])[0]))
                line_nos.append(i + 1)
                i += 1
            if len(vals) >= 2:
                groups.append((f"bullet-list@L{start+1}", vals, line_nos))
        else:
            i += 1
    return groups


def find_inline_groups(lines: List[str]) -> List[Tuple[str, List[float], List[int]]]:
    groups = []
    for idx, line in enumerate(lines):
        if BULLET_RE.match(line):
            continue
        pcts = PCT_RE.findall(line)
        # require >=3 inline and at least one comma/semicolon separator
        if len(pcts) >= 3 and (line.count(",") + line.count(";")) >= len(pcts) - 1:
            vals = [float(p) for p in pcts]
            groups.append((f"inline@L{idx+1}", vals, [idx + 1] * len(vals)))
    return groups


def find_table_groups(lines: List[str]) -> List[Tuple[str, List[float], List[int]]]:
    groups = []
    i = 0
    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            # markdown table header
            header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            ncol = len(header)
            data_start = i + 2
            j = data_start
            rows = []
            while j < len(lines) and "|" in lines[j]:
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if len(cells) == ncol:
                    rows.append((j + 1, cells))
                j += 1
            for col_idx in range(ncol):
                col_vals = []
                col_lines = []
                ok = True
                for line_no, cells in rows:
                    pcts = PCT_RE.findall(cells[col_idx])
                    if len(pcts) != 1 or cells[col_idx].replace(" ", "") != pcts[0] + "%":
                        ok = False
                        break
                    col_vals.append(float(pcts[0]))
                    col_lines.append(line_no)
                if ok and len(col_vals) >= 2:
                    label = header[col_idx] if col_idx < len(header) else f"col{col_idx}"
                    groups.append((f"table-col[{label}]@L{i+1}", col_vals, col_lines))
            i = j
        else:
            i += 1
    return groups


def main() -> int:
    text = sys.stdin.read()
    lines = text.splitlines()

    groups = []
    groups += find_bullet_groups(lines)
    groups += find_table_groups(lines)
    groups += find_inline_groups(lines)

    findings = []
    for label, vals, line_nos in groups:
        total = round(sum(vals), 4)
        drift = round(total - 100.0, 4)
        ok = abs(drift) <= TOLERANCE
        findings.append({
            "group": label,
            "values": vals,
            "lines": line_nos,
            "sum": total,
            "drift_from_100": drift,
            "ok": ok,
        })

    bad = [f for f in findings if not f["ok"]]
    report = {
        "tolerance_pp": TOLERANCE,
        "groups_checked": len(findings),
        "groups_failing": len(bad),
        "findings": findings,
    }
    print(json.dumps(report, indent=2))
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())

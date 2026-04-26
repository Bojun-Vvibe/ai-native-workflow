#!/usr/bin/env python3
"""Detect stale TODO/FIXME/XXX/HACK markers in supposedly-final LLM output.

Failure mode: an LLM is asked to produce a final deliverable (spec, doc,
PR description, code), but the generated content still contains placeholder
markers like TODO, FIXME, XXX, HACK, TBD, '<placeholder>', '???', or the
literal string '...' on a line by itself. These leak into shipped artifacts.

Reads stdin or a file path. Exit 0 if clean, 1 if findings.
"""
import re
import sys


# Word-boundary patterns. Case-sensitive on purpose — we want the loud
# ALL-CAPS markers, not the noun "todo" in prose.
WORD_MARKERS = ["TODO", "FIXME", "XXX", "HACK", "TBD", "WIP", "REVISIT"]
WORD_RE = re.compile(r"\b(" + "|".join(WORD_MARKERS) + r")\b")
ANGLE_PLACEHOLDER_RE = re.compile(r"<(placeholder|fill[-_ ]?in|insert[^>]*|your[^>]*|name[^>]*here)>", re.IGNORECASE)
TRIPLE_QUESTION_RE = re.compile(r"\?{3,}")
ELLIPSIS_LINE_RE = re.compile(r"^\s*\.{3,}\s*$")


def find_findings(text):
    findings = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in WORD_RE.finditer(line):
            findings.append({"line": i, "kind": f"word:{m.group(1)}", "preview": line.strip()[:80]})
        for m in ANGLE_PLACEHOLDER_RE.finditer(line):
            findings.append({"line": i, "kind": f"angle-placeholder:{m.group(0)}", "preview": line.strip()[:80]})
        if TRIPLE_QUESTION_RE.search(line):
            findings.append({"line": i, "kind": "triple-question-mark", "preview": line.strip()[:80]})
        if ELLIPSIS_LINE_RE.match(line):
            findings.append({"line": i, "kind": "lone-ellipsis-line", "preview": line.strip()[:80]})
    return findings


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    findings = find_findings(text)
    if not findings:
        print("clean: no stale TODO/placeholder markers found")
        return 0

    print(f"FOUND {len(findings)} stale-marker finding(s):")
    for f in findings:
        print(f"  line {f['line']} [{f['kind']}]: {f['preview']!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

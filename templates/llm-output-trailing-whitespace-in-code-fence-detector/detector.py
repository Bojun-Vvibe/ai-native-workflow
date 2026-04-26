#!/usr/bin/env python3
"""Detect trailing whitespace on lines inside fenced code blocks.

Failure mode: LLM output frequently contains trailing spaces/tabs on lines
inside ``` fenced code blocks. These are invisible in rendered markdown but
break diff hygiene, fail lint hooks, and corrupt copy-pasted shell commands
(trailing spaces after a backslash continuation silently break the line join).

Reads stdin or a file path. Exit 0 if clean, 1 if findings.
"""
import sys


FENCE_PREFIXES = ("```", "~~~")


def find_findings(text):
    findings = []
    in_fence = False
    fence_marker = None
    fence_start_line = 0
    for i, line in enumerate(text.splitlines(), start=1):
        stripped_lead = line.lstrip()
        if not in_fence:
            for marker in FENCE_PREFIXES:
                if stripped_lead.startswith(marker):
                    in_fence = True
                    fence_marker = marker
                    fence_start_line = i
                    break
            continue
        # inside a fence
        if stripped_lead.startswith(fence_marker) and stripped_lead[len(fence_marker):].strip() == "":
            in_fence = False
            fence_marker = None
            continue
        # check trailing whitespace
        rstripped = line.rstrip(" \t")
        if rstripped != line:
            trailing = line[len(rstripped):]
            kinds = []
            if " " in trailing:
                kinds.append(f"{trailing.count(' ')} space(s)")
            if "\t" in trailing:
                kinds.append(f"{trailing.count(chr(9))} tab(s)")
            findings.append({
                "line": i,
                "fence_started_at": fence_start_line,
                "trailing": ", ".join(kinds),
                "content_preview": rstripped[:60],
            })
    return findings


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    findings = find_findings(text)
    if not findings:
        print("clean: no trailing whitespace inside fenced code blocks")
        return 0

    print(f"FOUND {len(findings)} trailing-whitespace finding(s) inside fenced code blocks:")
    for f in findings:
        print(
            f"  line {f['line']} (fence opened at line {f['fence_started_at']}): "
            f"{f['trailing']} trailing | preview: {f['content_preview']!r}"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())

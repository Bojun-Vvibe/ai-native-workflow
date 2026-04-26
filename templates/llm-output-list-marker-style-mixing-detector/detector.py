"""Pure-stdlib detector for mixed unordered-list marker styles in LLM output.

Markdown allows three unordered-list markers: `-`, `*`, and `+`. Any
single list should pick one and stick with it. LLMs commonly drift
mid-list — emitting `-` for the first three items, then `*` for the
fourth (often after a paragraph break the model "forgot" was inside a
list). The result renders fine on most renderers but reads as two
adjacent lists, breaks list-counting downstream tools, and looks
sloppy in any committed doc.

This detector groups consecutive top-level (or same-indent-level)
unordered-list items into "list runs" and flags any run that uses
more than one distinct marker.

Findings:

- `mixed_unordered_list_markers` — one finding per drifted run.
  Includes the line range, the marker tally, and the line numbers
  where the marker switched.

Fenced code blocks (``` or ~~~) are skipped wholesale. Ordered list
items (`1.`, `2.`) are out of scope here — see
`llm-output-markdown-ordered-list-numbering-monotonicity-validator`.

Usage:
    python3 detector.py [FILE ...]   # files, or stdin if none
    exit 0 = clean, exit 1 = findings (JSON on stdout)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict

FENCE_RE = re.compile(r"^\s*(```|~~~)")
# A bullet line: optional indent (spaces only), one of - * +, then a
# space or tab (so `*emphasis*` isn't picked up).
BULLET_RE = re.compile(r"^(?P<indent> *)(?P<marker>[-*+])(?:[ \t]|$)")


@dataclass
class Finding:
    kind: str
    start_line: int
    end_line: int
    indent: int
    marker_tally: dict
    switch_lines: list

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Run:
    indent: int
    items: list = field(default_factory=list)  # list of (lineno, marker)


def _flush(run: _Run, findings: list[Finding]) -> None:
    if not run.items:
        return
    markers = [m for _, m in run.items]
    distinct = sorted(set(markers))
    if len(distinct) <= 1:
        return
    tally: dict = {}
    for m in markers:
        tally[m] = tally.get(m, 0) + 1
    # Switch lines: lines where the marker differs from the previous item.
    switch_lines: list = []
    prev = markers[0]
    for lineno, m in run.items[1:]:
        if m != prev:
            switch_lines.append(lineno)
            prev = m
    findings.append(
        Finding(
            kind="mixed_unordered_list_markers",
            start_line=run.items[0][0],
            end_line=run.items[-1][0],
            indent=run.indent,
            marker_tally=tally,
            switch_lines=switch_lines,
        )
    )


def detect_mixed_markers(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    findings: list[Finding] = []
    in_fence = False
    # We track one open run per indent level. A blank line between
    # bullets at the same indent does NOT terminate the run (Markdown
    # treats it as a "loose list"). A non-blank, non-bullet line at
    # that indent or shallower DOES terminate it.
    runs: dict[int, _Run] = {}
    blank_streak = 0

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            # A fence inside a list ends all runs at any indent.
            for r in runs.values():
                _flush(r, findings)
            runs.clear()
            blank_streak = 0
            continue
        if in_fence:
            continue

        stripped = raw.strip()
        if stripped == "":
            blank_streak += 1
            # Two consecutive blanks definitely end any run.
            if blank_streak >= 2:
                for r in runs.values():
                    _flush(r, findings)
                runs.clear()
            continue

        m = BULLET_RE.match(raw)
        if not m:
            # Non-bullet content. Close runs whose indent is >=
            # this line's leading-space count (this line is at or
            # outside that list level).
            leading = len(raw) - len(raw.lstrip(" "))
            to_close = [ind for ind in runs if ind >= leading]
            for ind in to_close:
                _flush(runs[ind], findings)
                del runs[ind]
            blank_streak = 0
            continue

        indent = len(m.group("indent"))
        marker = m.group("marker")
        # If we hit a bullet, close any deeper-or-equal runs at OTHER
        # indents that are siblings (a sibling at a different indent
        # is a new sub-list, not a continuation). Specifically, close
        # runs with indent > this indent (we're popping out).
        for ind in [k for k in runs if k > indent]:
            _flush(runs[ind], findings)
            del runs[ind]

        run = runs.get(indent)
        if run is None:
            run = _Run(indent=indent)
            runs[indent] = run
        run.items.append((lineno, marker))
        blank_streak = 0

    # EOF: flush remaining.
    for r in runs.values():
        _flush(r, findings)

    # Sort by start_line so output is deterministic.
    findings.sort(key=lambda f: (f.start_line, f.indent))
    return findings


def _read_inputs(argv: list[str]) -> str:
    if len(argv) <= 1:
        return sys.stdin.read()
    chunks = []
    for path in argv[1:]:
        with open(path, "r", encoding="utf-8") as fh:
            chunks.append(fh.read())
    return "\n".join(chunks)


def main(argv: list[str]) -> int:
    text = _read_inputs(argv)
    findings = detect_mixed_markers(text)
    payload = {
        "findings": [f.to_dict() for f in findings],
        "count": len(findings),
        "ok": len(findings) == 0,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

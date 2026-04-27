"""llm-output-markdown-fence-orphan-closing-detector

Pure stdlib detector that scans a markdown document produced by an
LLM for orphaned / mismatched fenced-code-block delimiters. The
failure modes it catches:

  - `orphan_close`     : a closing fence (` ``` ` or `~~~`) appears
                          on a line where no fence is currently open.
                          Renderers either swallow the line or start
                          a new code block from there to EOF.
  - `unterminated_open`: a fence is opened and the document ends
                          without ever closing it. Everything after
                          the opener is silently rendered as code.
  - `marker_mismatch`  : an opener uses one marker family
                          (` ``` `) but the next non-content line
                          that *looks* like a closer uses the other
                          family (`~~~`). CommonMark requires the
                          closer to use the same marker character
                          and at least the same count.
  - `count_mismatch`   : opener uses 4+ backticks (e.g. ```` ```` ````)
                          but the would-be closer uses fewer (e.g.
                          ` ``` `). The shorter run does not close
                          the block; the rest of the doc becomes
                          code.
  - `info_on_close`    : a closing fence carries an info string
                          (` ```python `). Closers must be bare;
                          anything after the marker is ignored or
                          interpreted differently across renderers.

These bugs are pernicious because the document still *parses* — it
just renders unrecognisably. A single orphan closer on line 30 can
turn the entire remainder of a 500-line answer into a grey code
block that nobody reads.

Stdlib only. Pure function over a string. Findings sorted by
`(kind, line_no, detail)` so two runs over the same input produce
byte-identical output (cron-friendly diffing).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple


class FenceValidationError(ValueError):
    """Raised eagerly on bad input type."""


@dataclass(frozen=True)
class Finding:
    kind: str       # orphan_close | unterminated_open |
                    # marker_mismatch | count_mismatch | info_on_close
    line_no: int    # 1-indexed
    detail: str


@dataclass
class FenceReport:
    ok: bool
    fences: List[Dict[str, object]] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "fences": self.fences,
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            sort_keys=True,
        )


def _classify_fence_line(line: str) -> Optional[Tuple[str, int, str]]:
    """If line is a CommonMark fence line, return (marker, run_len, info).

    Otherwise None. Allows up to 3 leading spaces of indent (more
    than that becomes an indented-code-block in CommonMark and is
    not a fence).
    """
    # strip up to 3 leading spaces
    i = 0
    while i < 3 and i < len(line) and line[i] == " ":
        i += 1
    rest = line[i:]
    if not rest:
        return None
    ch = rest[0]
    if ch not in ("`", "~"):
        return None
    j = 0
    while j < len(rest) and rest[j] == ch:
        j += 1
    if j < 3:
        return None
    info = rest[j:].rstrip("\n").rstrip("\r")
    # CommonMark: backtick fence info must not contain a backtick.
    # If it does, this is not a fence.
    if ch == "`" and "`" in info:
        return None
    return (ch, j, info.strip())


def check(text: str) -> FenceReport:
    if not isinstance(text, str):
        raise FenceValidationError("input must be str")

    findings: List[Finding] = []
    fences: List[Dict[str, object]] = []

    open_marker: Optional[str] = None  # "`" or "~"
    open_run: int = 0
    open_line: int = 0
    open_info: str = ""

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        cls = _classify_fence_line(raw_line)
        if cls is None:
            continue
        marker, run_len, info = cls

        if open_marker is None:
            # Looking for an opener. This line opens a fence.
            open_marker = marker
            open_run = run_len
            open_line = idx
            open_info = info
            continue

        # A fence is currently open. Decide if this line closes it.
        # Must be same marker family, run >= opener's run, info empty.
        if marker != open_marker:
            findings.append(Finding(
                kind="marker_mismatch",
                line_no=idx,
                detail=(
                    f"closer uses '{marker}' but opener at line "
                    f"{open_line} uses '{open_marker}'"
                ),
            ))
            # Treat as not-a-closer; stay open.
            continue
        if run_len < open_run:
            findings.append(Finding(
                kind="count_mismatch",
                line_no=idx,
                detail=(
                    f"closer has run of {run_len} '{marker}' but "
                    f"opener at line {open_line} has run of "
                    f"{open_run}"
                ),
            ))
            continue
        if info:
            findings.append(Finding(
                kind="info_on_close",
                line_no=idx,
                detail=(
                    f"closing fence carries info string {info!r}; "
                    f"closers must be bare"
                ),
            ))
            # Still treat it as a closer (lenient close), so the
            # rest of the doc parses sensibly.
        fences.append({
            "open_line": open_line,
            "close_line": idx,
            "marker": open_marker,
            "run": open_run,
            "info": open_info,
        })
        open_marker = None
        open_run = 0
        open_line = 0
        open_info = ""

    if open_marker is not None:
        findings.append(Finding(
            kind="unterminated_open",
            line_no=open_line,
            detail=(
                f"fence opened with run of {open_run} '{open_marker}'"
                f" never closed before EOF"
            ),
        ))
        fences.append({
            "open_line": open_line,
            "close_line": None,
            "marker": open_marker,
            "run": open_run,
            "info": open_info,
        })

    # Second pass for orphan closers: any fence-line outside a
    # tracked fence span. We re-walk because the forward scan above
    # consumes the first opener it sees; an orphan-close at the very
    # top of the doc would otherwise be miscategorised as an opener.
    open_spans = [
        (f["open_line"], f["close_line"] or 10**9) for f in fences
    ]

    def _inside_span(ln: int) -> bool:
        for lo, hi in open_spans:
            if lo <= ln <= hi:
                return True
        return False

    # Detect orphan closers: a fence line that is not the open_line
    # of any tracked span, and not within any span.
    open_lines = {f["open_line"] for f in fences}
    close_lines = {
        f["close_line"] for f in fences if f["close_line"] is not None
    }

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        cls = _classify_fence_line(raw_line)
        if cls is None:
            continue
        if idx in open_lines or idx in close_lines:
            continue
        if _inside_span(idx):
            continue
        marker, run_len, info = cls
        findings.append(Finding(
            kind="orphan_close",
            line_no=idx,
            detail=(
                f"fence line ('{marker}'x{run_len}) appears with no"
                f" matching opener"
            ),
        ))

    findings.sort(key=lambda f: (f.kind, f.line_no, f.detail))
    return FenceReport(ok=(len(findings) == 0), fences=fences, findings=findings)


# ---------------------------------------------------------------- demo

_CASES: List[Tuple[str, str]] = [
    (
        "01_clean",
        "# Title\n\n"
        "Some prose.\n\n"
        "```python\n"
        "print('hi')\n"
        "```\n\n"
        "More prose.\n\n"
        "~~~\n"
        "raw block\n"
        "~~~\n",
    ),
    (
        "02_unterminated_open",
        "# Title\n\n"
        "```python\n"
        "x = 1\n"
        "y = 2\n"
        "# end of doc, no closing fence\n",
    ),
    (
        "03_orphan_close",
        "# Title\n\n"
        "Some prose with no fence open.\n\n"
        "```\n\n"
        "More prose. The line above orphan-closes.\n",
    ),
    (
        "04_marker_mismatch",
        "# Title\n\n"
        "```python\n"
        "print('hi')\n"
        "~~~\n"
        "still inside the backtick fence\n"
        "```\n",
    ),
    (
        "05_count_mismatch",
        "# Title\n\n"
        "````\n"
        "code with ``` inside\n"
        "```\n"
        "more code, the 3-tick line did not close us\n"
        "````\n",
    ),
    (
        "06_info_on_close",
        "# Title\n\n"
        "```python\n"
        "x = 1\n"
        "```python\n",
    ),
]


def _run_demo() -> int:
    print("# llm-output-markdown-fence-orphan-closing-detector"
          " — worked example")
    print()
    any_failed = False
    for name, src in _CASES:
        print(f"## case {name}")
        print(f"input_lines: {len(src.splitlines())}")
        report = check(src)
        if not report.ok:
            any_failed = True
        print(report.to_json())
        print()
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(_run_demo())

"""llm-output-markdown-heading-skip-level-detector — pure-stdlib detector.

Catches heading-level skips in LLM-generated markdown: a document that
goes from `#` straight to `###` (skipping `##`) is fluent prose that
silently breaks downstream TOC generators, accessibility tools, and
nested-section serializers. The model "knew" it wanted a sub-sub-section
but never emitted the parent.

Pure function. No regex. Stdlib only. ATX-style headings only
(`# `, `## `, ...); Setext (`===` / `---` underlines) intentionally
out of scope — a separate template handles those.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import List, Optional


class HeadingSkipDetectionError(ValueError):
    """Raised on bad input shape."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int  # 1-indexed
    detail: str


@dataclass(frozen=True)
class Result:
    headings: List[dict]
    findings: List[dict]
    ok: bool


def _strip_fenced_code(lines: List[str]) -> List[Optional[str]]:
    """Replace lines inside ``` ... ``` fences with None so heading
    parser ignores them. Tracks the fence char and length so a longer
    fence doesn't get closed by a shorter one inside it."""
    out: List[Optional[str]] = []
    fence_marker: Optional[str] = None  # e.g. "```" or "~~~~"
    for ln in lines:
        stripped = ln.lstrip()
        if fence_marker is None:
            # opening?
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = 0
                for c in stripped:
                    if c == ch:
                        run += 1
                    else:
                        break
                if run >= 3:
                    fence_marker = ch * run
                    out.append(None)
                    continue
            out.append(ln)
        else:
            ch = fence_marker[0]
            run = 0
            for c in stripped:
                if c == ch:
                    run += 1
                else:
                    break
            if run >= len(fence_marker) and stripped[run:].strip() == "":
                fence_marker = None
            out.append(None)
    return out


def detect(markdown: str, *, max_skip: int = 1) -> Result:
    """Scan ATX headings and report each forward jump > `max_skip`.

    `max_skip=1` (default): h1->h2 ok, h1->h3 flagged.
    `max_skip=2`: h1->h2->h3 ok, h1->h2->h5 flagged.

    Also reports a leading-skip if the very first heading is deeper
    than h1 — many tools (and most accessibility checkers) want a
    document to start at h1.
    """
    if not isinstance(markdown, str):
        raise HeadingSkipDetectionError("markdown must be a str")
    if not isinstance(max_skip, int) or max_skip < 1:
        raise HeadingSkipDetectionError("max_skip must be int >= 1")

    raw_lines = markdown.split("\n")
    code_aware = _strip_fenced_code(raw_lines)

    headings: List[dict] = []
    findings: List[Finding] = []

    for idx, ln in enumerate(code_aware):
        if ln is None:
            continue
        # ATX heading: 0–3 leading spaces, then 1–6 '#', then space or EOL
        i = 0
        while i < len(ln) and i < 3 and ln[i] == " ":
            i += 1
        if i >= len(ln) or ln[i] != "#":
            continue
        hashes = 0
        while i + hashes < len(ln) and ln[i + hashes] == "#":
            hashes += 1
        if hashes < 1 or hashes > 6:
            continue
        rest = ln[i + hashes:]
        if rest != "" and not rest.startswith(" ") and not rest.startswith("\t"):
            # e.g. "##bold" — not a heading per CommonMark
            continue
        text = rest.strip()
        # trailing closing hashes are allowed in ATX; strip them
        if text.endswith("#"):
            j = len(text)
            while j > 0 and text[j - 1] == "#":
                j -= 1
            tail = text[j:]
            head = text[:j].rstrip()
            if head == "" or head.endswith(" "):
                text = head.rstrip()
            else:
                text = head + tail  # no preceding space → not a closer
        headings.append({"line": idx + 1, "level": hashes, "text": text})

    # sequence checks
    prev_level: Optional[int] = None
    for h in headings:
        lvl = h["level"]
        if prev_level is None:
            if lvl > 1:
                findings.append(
                    Finding(
                        kind="leading_skip",
                        line=h["line"],
                        detail=f"document starts at h{lvl}, expected h1",
                    )
                )
        else:
            jump = lvl - prev_level
            if jump > max_skip:
                findings.append(
                    Finding(
                        kind="skip_level",
                        line=h["line"],
                        detail=f"h{prev_level} -> h{lvl} (jump of {jump}, max_skip={max_skip})",
                    )
                )
        prev_level = lvl

    findings_sorted = sorted(
        (asdict(f) for f in findings),
        key=lambda d: (d["kind"], d["line"], d["detail"]),
    )
    return Result(headings=headings, findings=findings_sorted, ok=not findings_sorted)


_CASES = [
    (
        "01_clean",
        "# Title\n\nIntro.\n\n## Section\n\nBody.\n\n### Subsection\n\nMore body.\n\n## Another\n",
        1,
    ),
    (
        "02_h1_to_h3",
        "# Title\n\nIntro.\n\n### Buried subsection — model forgot the ## parent\n\nBody.\n",
        1,
    ),
    (
        "03_leading_h2",
        "## Starts deep\n\nBody.\n\n### Child\n",
        1,
    ),
    (
        "04_multiple_skips",
        "# Top\n\n### Skipped once\n\nBody.\n\n###### Skipped again\n",
        1,
    ),
    (
        "05_descents_are_fine",
        "# A\n\n## B\n\n### C\n\n# D\n\n## E\n",
        1,
    ),
    (
        "06_inside_fenced_code_ignored",
        "# Real heading\n\n```\n# not a heading\n### also not\n```\n\n## Sibling\n",
        1,
    ),
    (
        "07_max_skip_2_allows_h1_to_h3",
        "# Top\n\n### Two-level jump\n\n#### Child\n",
        2,
    ),
]


def _main() -> None:
    print("# llm-output-markdown-heading-skip-level-detector — worked example\n")
    for name, md, max_skip in _CASES:
        print(f"## case {name}")
        print(f"max_skip={max_skip}")
        print("markdown:")
        for ln in md.rstrip("\n").split("\n"):
            print(f"  | {ln}")
        result = detect(md, max_skip=max_skip)
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        print()


if __name__ == "__main__":
    _main()

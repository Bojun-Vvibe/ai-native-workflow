"""llm-output-markdown-heading-level-skip-detector

Pure stdlib detector that scans a markdown document produced by an
LLM for heading-level structural smells. The failure mode it catches:
the model writes a doc that *looks* tidy in a rendered preview but
its heading tree is broken — `##` jumps straight to `####`, the doc
opens at `###` with no `#` parent, two consecutive `#` headings
appear with no body between them, the same heading text repeats at
the same level (anchor collisions), or a heading line is empty.

These bugs degrade screen-reader navigation, break TOC generation,
poison downstream chunkers that key on heading depth, and confuse
RAG retrievers that use heading paths as document IDs.

Heading-fence-aware: lines inside ``` fenced code blocks are NOT
parsed as headings. ATX style only (`#`-prefixed). Setext style
(underlined with `===` / `---`) is intentionally out of scope —
modern LLM output is essentially 100% ATX.

Stdlib only. Pure function over a string. Findings sorted by
`(kind, line_no, detail)` so two runs over the same input produce
byte-identical output (cron-friendly diffing).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple


class HeadingValidationError(ValueError):
    """Raised eagerly on bad input type."""


@dataclass(frozen=True)
class Finding:
    kind: str       # one of: level_skip, no_root, empty_heading,
                    # adjacent_headings, duplicate_anchor,
                    # trailing_hashes
    line_no: int    # 1-indexed line number of the offending heading
    detail: str


@dataclass
class HeadingReport:
    ok: bool
    headings: List[Dict[str, object]] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "headings": self.headings,
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            sort_keys=True,
        )


def _slugify(text: str) -> str:
    """GitHub-flavored anchor slug (lowercase, spaces→dashes, drop punctuation)."""
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
        # else: drop
    slug = "".join(out)
    # collapse runs of dashes
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _parse_heading(line: str) -> Tuple[int, str, bool] | None:
    """Return (level, text, had_trailing_hashes) or None if not a heading.

    Recognizes ATX headings: 1-6 leading `#` followed by a space.
    A line of only `#`s (no text) is still recognized as an empty
    heading at that level (so we can flag it).
    """
    stripped = line.lstrip()
    # leading whitespace > 3 spaces would be a code block in CommonMark
    if len(line) - len(stripped) >= 4:
        return None
    if not stripped.startswith("#"):
        return None
    i = 0
    while i < len(stripped) and stripped[i] == "#" and i < 7:
        i += 1
    if i == 0 or i > 6:
        return None
    rest = stripped[i:]
    # Must be EOL or a space after the #s (CommonMark requirement)
    if rest and not rest.startswith(" "):
        return None
    text = rest.strip()
    had_trailing = False
    # Strip closing #s (ATX closing sequence): trailing run of #s
    # preceded by a space, e.g. "## Title ##"
    if text.endswith("#"):
        # find last non-# char
        j = len(text) - 1
        while j >= 0 and text[j] == "#":
            j -= 1
        if j >= 0 and text[j] == " ":
            had_trailing = True
            text = text[:j].rstrip()
        elif j < 0:
            # whole thing was #s — empty heading expressed as `## ##`
            had_trailing = True
            text = ""
    return (i, text, had_trailing)


def check(markdown: str) -> HeadingReport:
    """Audit heading structure of a markdown document.

    Args:
        markdown: full markdown document as a string.

    Returns:
        HeadingReport with `ok=False` iff any finding fires.
    """
    if not isinstance(markdown, str):
        raise HeadingValidationError(
            f"markdown must be str, got {type(markdown).__name__}"
        )

    lines = markdown.splitlines()
    in_fence = False
    fence_marker = ""

    parsed: List[Tuple[int, int, str, bool]] = []  # (line_no, level, text, trailing)
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        # fenced code block toggle (```/~~~ with optional info string)
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            fence_marker = stripped[:3]
            in_fence = True
            continue
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
            continue
        h = _parse_heading(line)
        if h is None:
            continue
        level, text, trailing = h
        parsed.append((i, level, text, trailing))

    findings: List[Finding] = []
    headings_out: List[Dict[str, object]] = []
    seen_anchor_at_level: Dict[Tuple[int, str], int] = {}
    prev_level: int | None = None
    prev_line_no: int | None = None
    last_body_line_no: int = 0  # last non-blank, non-heading line we saw

    # Re-scan to track body content interleaved with headings
    parsed_set = {ln for ln, _, _, _ in parsed}
    body_after: Dict[int, bool] = {}  # heading line_no -> "non-empty body before next heading?"
    sorted_headings = sorted(parsed_set)
    for idx, hline in enumerate(sorted_headings):
        nxt = sorted_headings[idx + 1] if idx + 1 < len(sorted_headings) else len(lines) + 1
        had_body = False
        in_fence_local = False
        fm = ""
        for j in range(hline + 1, nxt):
            raw = lines[j - 1]
            s = raw.strip()
            if not in_fence_local and (s.startswith("```") or s.startswith("~~~")):
                in_fence_local = True
                fm = s[:3]
                had_body = True
                continue
            if in_fence_local:
                if s.startswith(fm):
                    in_fence_local = False
                continue
            if s:
                had_body = True
                break
        body_after[hline] = had_body

    for line_no, level, text, trailing in parsed:
        anchor = _slugify(text) if text else ""
        headings_out.append(
            {
                "line_no": line_no,
                "level": level,
                "text": text,
                "anchor": anchor,
            }
        )

        # empty_heading
        if not text:
            findings.append(
                Finding(
                    "empty_heading",
                    line_no,
                    f"H{level} heading has no text",
                )
            )

        # trailing_hashes (style smell, not a structural break)
        if trailing:
            findings.append(
                Finding(
                    "trailing_hashes",
                    line_no,
                    f"H{level} heading uses ATX-closing '#' run",
                )
            )

        # no_root: very first heading must be H1
        if prev_level is None and level != 1:
            findings.append(
                Finding(
                    "no_root",
                    line_no,
                    f"document opens at H{level} with no H1 ancestor",
                )
            )

        # level_skip: jumping more than 1 level deeper
        if prev_level is not None and level > prev_level + 1:
            findings.append(
                Finding(
                    "level_skip",
                    line_no,
                    f"jumped from H{prev_level} to H{level} (skipped {level - prev_level - 1})",
                )
            )

        # adjacent_headings: two headings with no body between them
        if prev_line_no is not None and not body_after.get(prev_line_no, True):
            findings.append(
                Finding(
                    "adjacent_headings",
                    line_no,
                    f"H{level} immediately follows previous heading at line {prev_line_no} with no body",
                )
            )

        # duplicate_anchor: same slug at same level
        if anchor:
            key = (level, anchor)
            if key in seen_anchor_at_level:
                first = seen_anchor_at_level[key]
                findings.append(
                    Finding(
                        "duplicate_anchor",
                        line_no,
                        f"H{level} anchor '{anchor}' duplicates line {first}",
                    )
                )
            else:
                seen_anchor_at_level[key] = line_no

        prev_level = level
        prev_line_no = line_no

    findings.sort(key=lambda f: (f.kind, f.line_no, f.detail))
    return HeadingReport(ok=not findings, headings=headings_out, findings=findings)


# ---------------------------------------------------------------------------
# Worked example
# ---------------------------------------------------------------------------

_CASES = [
    (
        "01_clean",
        "# Title\n\nIntro paragraph.\n\n## Section A\n\nBody.\n\n### Subsection\n\nMore body.\n\n## Section B\n\nDone.\n",
    ),
    (
        "02_level_skip",
        "# Title\n\nIntro.\n\n## Section\n\nBody.\n\n#### Way too deep\n\nText.\n",
    ),
    (
        "03_no_root",
        "## Subsection without parent\n\nBody.\n\n### Deeper\n\nMore.\n",
    ),
    (
        "04_empty_and_trailing",
        "# Title\n\nIntro.\n\n## \n\nBody under empty heading.\n\n### Closed Style ###\n\nMore.\n",
    ),
    (
        "05_adjacent_no_body",
        "# Title\n\n## First\n## Second\n\nBody finally.\n",
    ),
    (
        "06_duplicate_anchor",
        "# Doc\n\nIntro paragraph.\n\n## Notes\n\nFirst notes.\n\n## Notes\n\nSecond notes (collides).\n",
    ),
    (
        "07_fence_aware",
        # Heading-looking lines inside a fence MUST be ignored
        "# Title\n\n```python\n# this is a comment, not a heading\n## also not a heading\n```\n\n## Real Section\n\nBody.\n",
    ),
]


def _run_demo() -> None:
    print("# llm-output-markdown-heading-level-skip-detector — worked example")
    print()
    for name, doc in _CASES:
        print(f"## case {name}")
        print(f"input_lines: {len(doc.splitlines())}")
        result = check(doc)
        print(result.to_json())
        print()


if __name__ == "__main__":
    _run_demo()

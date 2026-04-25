"""prompt-drift-detector

Detect when an in-flight prompt has *drifted* from a pinned baseline
prompt. Drift here means structural change — sections appeared or
disappeared, ordering changed, line counts shifted beyond a
threshold — not random word-level edits.

The use case: you ship a long system prompt with named sections
(`# Identity`, `# Tools`, `# Output format`, …). Over time the
prompt is edited from many places (templating, runtime injection,
copy-paste from another mission, an agent helpfully "improving" it).
Before the prompt goes out, you want a fast structural diff that
flags the *kind* of change, not just "it's different."

Stdlib only. Pure: returns a new report, never mutates inputs.
Deterministic: same baseline + candidate always produce the same
report.

## Section model

A "section" is a contiguous run of lines whose first line matches
the configurable header pattern (default: `^#{1,6}\\s+\\S`, i.e.
ATX-style markdown headers). Section identity is the *header text*
after stripping leading `#` and whitespace, lower-cased — so
renaming a header is treated as `removed(old) + added(new)`, which
is what you want for drift purposes.

Pre-header content (anything before the first header) is treated as
a synthetic section named `__preamble__`.

## Drift signals

For each baseline section also present in the candidate, compute a
`line_delta` (candidate lines minus baseline lines). The detector
emits four classes:

* `added_sections` — present in candidate, absent in baseline.
* `removed_sections` — present in baseline, absent in candidate.
* `reordered_sections` — order of the *common* section names
  changed.
* `expanded_or_shrunk` — common section whose `line_delta` exceeds
  the configurable threshold (default ±5 lines or ±50%, whichever
  is larger).

`is_drifted` is true iff *any* class is non-empty. The caller
decides what to do — log, block, page, fall back to the pinned
baseline prompt — based on which signals fired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_HEADER_RE = re.compile(r"^#{1,6}\s+(\S.*)$")
PREAMBLE = "__preamble__"


@dataclass(frozen=True)
class SectionDelta:
    name: str
    baseline_lines: int
    candidate_lines: int
    line_delta: int


@dataclass(frozen=True)
class DriftReport:
    is_drifted: bool
    added_sections: tuple[str, ...]
    removed_sections: tuple[str, ...]
    reordered_sections: bool
    expanded_or_shrunk: tuple[SectionDelta, ...]
    baseline_section_order: tuple[str, ...] = field(default_factory=tuple)
    candidate_section_order: tuple[str, ...] = field(default_factory=tuple)


def _split_sections(
    text: str, header_re: re.Pattern[str]
) -> "list[tuple[str, list[str]]]":
    """Split `text` into [(name, lines), …] preserving order."""
    sections: "list[tuple[str, list[str]]]" = []
    current_name = PREAMBLE
    current_lines: "list[str]" = []
    for raw in text.splitlines():
        m = header_re.match(raw)
        if m is None:
            current_lines.append(raw)
            continue
        # Flush current.
        sections.append((current_name, current_lines))
        current_name = m.group(1).strip().lower()
        current_lines = []
    sections.append((current_name, current_lines))
    # Drop empty preamble (no preamble content at all).
    if (
        sections
        and sections[0][0] == PREAMBLE
        and not any(line.strip() for line in sections[0][1])
    ):
        sections = sections[1:]
    return sections


def detect_drift(
    baseline: str,
    candidate: str,
    *,
    header_re: re.Pattern[str] = DEFAULT_HEADER_RE,
    abs_line_threshold: int = 5,
    rel_line_threshold: float = 0.5,
) -> DriftReport:
    """Return a structural drift report comparing `candidate` to `baseline`.

    A section is flagged as `expanded_or_shrunk` when
    `abs(line_delta) > max(abs_line_threshold, baseline_lines *
    rel_line_threshold)` — the larger of the two thresholds wins so
    a 2-line section can't trigger on a 3-line edit (relative would
    pass; absolute floor blocks it), and a 200-line section can't
    hide a 30-line edit (absolute would pass; relative floor blocks
    it).
    """
    if not isinstance(baseline, str) or not isinstance(candidate, str):
        raise TypeError("baseline and candidate must be str")
    if abs_line_threshold < 0:
        raise ValueError("abs_line_threshold must be >= 0")
    if rel_line_threshold < 0:
        raise ValueError("rel_line_threshold must be >= 0")

    base_sections = _split_sections(baseline, header_re)
    cand_sections = _split_sections(candidate, header_re)

    base_order = tuple(name for name, _ in base_sections)
    cand_order = tuple(name for name, _ in cand_sections)

    base_set = set(base_order)
    cand_set = set(cand_order)

    added = tuple(n for n in cand_order if n not in base_set)
    removed = tuple(n for n in base_order if n not in cand_set)

    common = [n for n in base_order if n in cand_set]
    common_in_cand = [n for n in cand_order if n in base_set]
    reordered = common != common_in_cand

    base_lines_by_name = {name: len(lines) for name, lines in base_sections}
    cand_lines_by_name = {name: len(lines) for name, lines in cand_sections}

    expanded_or_shrunk: "list[SectionDelta]" = []
    for name in common:
        bl = base_lines_by_name[name]
        cl = cand_lines_by_name[name]
        delta = cl - bl
        threshold = max(abs_line_threshold, int(bl * rel_line_threshold))
        if abs(delta) > threshold:
            expanded_or_shrunk.append(
                SectionDelta(
                    name=name,
                    baseline_lines=bl,
                    candidate_lines=cl,
                    line_delta=delta,
                )
            )

    is_drifted = bool(added or removed or reordered or expanded_or_shrunk)

    return DriftReport(
        is_drifted=is_drifted,
        added_sections=added,
        removed_sections=removed,
        reordered_sections=reordered,
        expanded_or_shrunk=tuple(expanded_or_shrunk),
        baseline_section_order=base_order,
        candidate_section_order=cand_order,
    )

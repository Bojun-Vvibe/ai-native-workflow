"""llm-output-list-marker-consistency-validator — pure stdlib.

Scans Markdown prose for unordered-list bullet groups that mix marker
characters within the *same* list, plus a few adjacent failure modes
(ordered-list numbering gap, indent jitter inside one list, switching
ordered<->unordered mid-list). One forward scan, no regex.

A "list group" here is a maximal run of consecutive lines, each of
which is a bullet (`- `, `* `, `+ `, or `<int>. `) at the *same
indent column*. A blank line, or a non-bullet line, ends the group.
A change in indent column starts a new group at the new column (and
the deeper one nests inside the shallower one — see `indent_jitter`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional


class ListMarkerValidationError(ValueError):
    """Raised eagerly on bad input (non-str prose)."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int  # 1-indexed
    detail: str


@dataclass
class Result:
    groups: int
    findings: List[Finding] = field(default_factory=list)
    ok: bool = True


_UNORDERED = {"-", "*", "+"}


def _classify(line: str):
    """Return (indent, marker, rest) or None if not a bullet line.

    marker is one of '-', '*', '+', or an int string like '1' for ordered.
    """
    i = 0
    n = len(line)
    while i < n and line[i] == " ":
        i += 1
    if i >= n:
        return None
    ch = line[i]
    if ch in _UNORDERED and i + 1 < n and line[i + 1] == " ":
        return (i, ch, line[i + 2 :])
    # ordered: digits then '. ' then space
    j = i
    while j < n and line[j].isdigit():
        j += 1
    if j > i and j + 1 < n and line[j] == "." and line[j + 1] == " ":
        return (i, line[i:j], line[j + 2 :])
    return None


def validate(prose: str) -> Result:
    if not isinstance(prose, str):
        raise ListMarkerValidationError("prose must be str")

    findings: List[Finding] = []
    lines = prose.split("\n")

    # group state
    g_indent: Optional[int] = None
    g_kind: Optional[str] = None  # 'unordered' or 'ordered'
    g_marker: Optional[str] = None  # the first unordered char OR the running ordered counter as str of last seen
    g_start_line: int = 0
    g_seen_ordered: List[int] = []
    groups_count = 0

    def close_group():
        nonlocal g_indent, g_kind, g_marker, g_start_line, g_seen_ordered, groups_count
        if g_indent is not None:
            groups_count += 1
            if g_kind == "ordered" and g_seen_ordered:
                expected = g_seen_ordered[0]
                for idx, n_seen in enumerate(g_seen_ordered):
                    if n_seen != expected + idx:
                        findings.append(
                            Finding(
                                kind="ordered_numbering_gap",
                                line=g_start_line + idx,
                                detail=(
                                    f"ordered list expected {expected + idx}. but got {n_seen}."
                                ),
                            )
                        )
                        break
        g_indent = None
        g_kind = None
        g_marker = None
        g_start_line = 0
        g_seen_ordered = []

    for li, raw in enumerate(lines, start=1):
        c = _classify(raw)
        if c is None:
            close_group()
            continue
        indent, marker, _rest = c
        kind = "unordered" if marker in _UNORDERED else "ordered"

        if g_indent is None:
            # start a new group
            g_indent = indent
            g_kind = kind
            g_marker = marker
            g_start_line = li
            if kind == "ordered":
                g_seen_ordered = [int(marker)]
            continue

        if indent != g_indent:
            # indent jitter inside what looks like one logical list
            findings.append(
                Finding(
                    kind="indent_jitter",
                    line=li,
                    detail=(
                        f"bullet at column {indent} after group started at column {g_indent}"
                    ),
                )
            )
            close_group()
            # restart at the new indent
            g_indent = indent
            g_kind = kind
            g_marker = marker
            g_start_line = li
            if kind == "ordered":
                g_seen_ordered = [int(marker)]
            continue

        # same indent column: must keep the same kind AND the same marker
        if kind != g_kind:
            findings.append(
                Finding(
                    kind="kind_switch",
                    line=li,
                    detail=(
                        f"switched from {g_kind} to {kind} mid-list (marker '{marker}')"
                    ),
                )
            )
        elif kind == "unordered" and marker != g_marker:
            findings.append(
                Finding(
                    kind="mixed_unordered_marker",
                    line=li,
                    detail=(
                        f"marker '{marker}' in a list that started with '{g_marker}'"
                    ),
                )
            )
        if kind == "ordered":
            g_seen_ordered.append(int(marker))

    close_group()

    findings.sort(key=lambda f: (f.kind, f.line, f.detail))
    return Result(groups=groups_count, findings=findings, ok=(not findings))


# ---------- worked example ----------

_CASES = [
    (
        "01_clean_dash",
        "Steps:\n- one\n- two\n- three\n",
    ),
    (
        "02_mixed_unordered_dash_then_star",
        "Pros:\n- fast\n* cheap\n- simple\n",
    ),
    (
        "03_mixed_dash_plus_star",
        "Notes:\n- alpha\n+ beta\n* gamma\n",
    ),
    (
        "04_ordered_numbering_gap",
        "Recipe:\n1. boil water\n2. add tea\n4. steep\n5. serve\n",
    ),
    (
        "05_kind_switch_mid_list",
        "Plan:\n- draft\n- review\n3. ship\n",
    ),
    (
        "06_indent_jitter",
        "Outline:\n- top\n  - nested\n - oddly indented\n",
    ),
    (
        "07_two_separate_clean_lists",
        "First list:\n- a\n- b\n\nSecond list:\n* x\n* y\n",
    ),
]


def _main():
    print("# llm-output-list-marker-consistency-validator — worked example")
    print()
    for name, prose in _CASES:
        print(f"## case {name}")
        # show prose with visible newlines
        print("prose:")
        for ln in prose.rstrip("\n").split("\n"):
            print(f"  | {ln}")
        try:
            r = validate(prose)
            payload = {
                "groups": r.groups,
                "findings": [asdict(f) for f in r.findings],
                "ok": r.ok,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        except ListMarkerValidationError as e:
            print(f"ERROR: {e}")
        print()


if __name__ == "__main__":
    _main()

"""llm-output-ordinal-sequence-gap-detector — pure stdlib.

Detects structural gaps in ordinal sequences inside LLM prose:

  - "First ... Second ... Fourth" (skipped 'Third')
  - "Step 1: ... Step 3:"        (skipped Step 2)
  - "1." then "2." then "4."     (numbered list with a hole)
  - "Step 2: ..."                (sequence does not start at 1)
  - duplicate ordinals ("Step 2 ... Step 2")

The model often emits prose that *reads* fluent but enumerates 1, 2, 4
because an intermediate item was deleted during a revision pass and the
remaining anchors were not reflowed. Downstream consumers ("extract the
N-th step", "render as a numbered HTML list", "verify the agent
completed all stages") then silently skip or misalign.

Single deterministic pass, no I/O, no third-party deps.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Iterable


# Ordinal words we recognise. Mapped to their integer position.
ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12,
}

# Sequence "kinds" — each is detected independently and reported with
# its own gap analysis so a single piece of prose using both
# "Step N:" and "First/Second/Third" gets two separate reports.
_PATTERNS = [
    # "Step 1:", "Step 2."  — case-insensitive, integer required
    ("step",     re.compile(r"\bStep\s+(\d+)\b", re.IGNORECASE)),
    # "Phase 1", "Phase 2"
    ("phase",    re.compile(r"\bPhase\s+(\d+)\b", re.IGNORECASE)),
    # "Stage 1"
    ("stage",    re.compile(r"\bStage\s+(\d+)\b", re.IGNORECASE)),
    # "Chapter 1"
    ("chapter",  re.compile(r"\bChapter\s+(\d+)\b", re.IGNORECASE)),
    # Numbered list lines:  "1." or "2)"  at start of a line
    ("numbered", re.compile(r"(?m)^\s*(\d+)[.)]\s+\S")),
    # Ordinal words: "First, ...", "Second:", "Third —"
    # Bound on right by punctuation/space; left by start-of-line or
    # whitespace to avoid matching "refirst".
    ("ordinal_word", re.compile(
        r"(?<![A-Za-z])(" + "|".join(ORDINAL_WORDS) + r")(?![A-Za-z])",
        re.IGNORECASE,
    )),
]


class OrdinalValidationError(ValueError):
    """Raised on structurally unusable input (not a string)."""


@dataclass(frozen=True)
class Finding:
    kind: str          # one of: missing, duplicate, does_not_start_at_one
    sequence: str      # which sequence: step / phase / numbered / ordinal_word / ...
    value: int         # the missing/duplicated/starting integer
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    ok: bool
    sequences: dict                # sequence_kind -> sorted list of seen integers
    findings: list                 # list[Finding]

    def kinds(self) -> list:
        return sorted({f.kind for f in self.findings})

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "sequences": {k: sorted(set(v)) for k, v in self.sequences.items()},
            "findings": [f.to_dict() for f in self.findings],
        }


def _extract(prose: str) -> dict:
    """Return {sequence_kind: [int, int, ...]} preserving duplicates."""
    out: dict = {}
    for kind, pat in _PATTERNS:
        seen = []
        for m in pat.finditer(prose):
            tok = m.group(1)
            if kind == "ordinal_word":
                seen.append(ORDINAL_WORDS[tok.lower()])
            else:
                seen.append(int(tok))
        if seen:
            out[kind] = seen
    return out


def validate_ordinal_sequences(
    prose: str,
    *,
    require_start_at_one: bool = True,
    flag_duplicates: bool = True,
) -> Report:
    """Validate every ordinal sequence found in prose.

    A "sequence" is a kind of ordinal anchor (step, phase, numbered
    list line, ordinal word). Each sequence is checked independently:

      - **missing**: integers between the min and max of the sequence
        that were never emitted (1,2,4 -> missing 3).
      - **duplicate**: same integer emitted twice in the same sequence.
      - **does_not_start_at_one**: min(seen) > 1 — only emitted when
        ``require_start_at_one=True``. Often a real bug ("Step 2"
        appearing alone usually means "Step 1" was dropped); set
        False for prose that legitimately picks up mid-sequence.

    Findings are sorted by ``(sequence, kind, value)`` so two runs over
    the same input produce byte-identical output.
    """
    if not isinstance(prose, str):
        raise OrdinalValidationError(
            f"prose must be str, got {type(prose).__name__}")

    sequences = _extract(prose)
    findings: list = []

    for kind, seen in sequences.items():
        unique_sorted = sorted(set(seen))
        if not unique_sorted:
            continue

        # Duplicates
        if flag_duplicates:
            counts: dict = {}
            for v in seen:
                counts[v] = counts.get(v, 0) + 1
            for v in sorted(counts):
                if counts[v] > 1:
                    findings.append(Finding(
                        kind="duplicate",
                        sequence=kind,
                        value=v,
                        detail=f"{kind} value {v} appears {counts[v]} times",
                    ))

        # Does not start at 1
        if require_start_at_one and unique_sorted[0] != 1:
            findings.append(Finding(
                kind="does_not_start_at_one",
                sequence=kind,
                value=unique_sorted[0],
                detail=(
                    f"{kind} sequence starts at {unique_sorted[0]} "
                    f"(expected 1)"
                ),
            ))

        # Missing values inside [min..max]
        full = set(range(unique_sorted[0], unique_sorted[-1] + 1))
        missing = sorted(full - set(unique_sorted))
        for v in missing:
            findings.append(Finding(
                kind="missing",
                sequence=kind,
                value=v,
                detail=(
                    f"{kind} sequence has gap: value {v} missing "
                    f"between {unique_sorted[0]} and {unique_sorted[-1]}"
                ),
            ))

    findings.sort(key=lambda f: (f.sequence, f.kind, f.value))
    ok = len(findings) == 0
    return Report(ok=ok, sequences=sequences, findings=findings)


# --------------------------- worked cases ---------------------------

CASES = [
    ("01 clean numbered list", """
Here is the plan:
1. Gather inputs.
2. Validate them.
3. Emit a report.
"""),
    ("02 step gap", """
Step 1: Read the file.
Step 2: Parse it.
Step 4: Write the result.
"""),
    ("03 ordinal words skip third", """
First, we read. Second, we parse. Fourth, we write the result.
"""),
    ("04 duplicate phase + does-not-start-at-one", """
Phase 2 begins by warming the cache. Phase 2 also primes the index.
Phase 3 runs the eval.
"""),
    ("05 mixed: numbered ok, step has gap", """
1. Open the input.
2. Process it.
3. Close it.

Internally:
Step 1: tokenize.
Step 3: serialize.
"""),
]


def main() -> None:
    for label, prose in CASES:
        print(f"--- {label} ---")
        rep = validate_ordinal_sequences(prose)
        print(json.dumps(rep.to_dict(), indent=2))
        print()

    print("=== summary ===")
    for label, prose in CASES:
        rep = validate_ordinal_sequences(prose)
        print(f"case {label.split()[0]}: ok={rep.ok} kinds={rep.kinds()}")


if __name__ == "__main__":
    main()

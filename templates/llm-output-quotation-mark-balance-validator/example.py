"""llm-output-quotation-mark-balance-validator — pure stdlib.

Detects unbalanced or mismatched quotation marks in LLM prose.

Quotes the model emits silently corrupt three downstream behaviours:

  - "extract everything inside double quotes" splits on the wrong
    spans when one closing quote was dropped.
  - "render to JSON" mistakes a curly “smart” quote for a literal
    character and emits invalid JSON.
  - "diff the model output against a reference" fires false-positives
    because one side uses straight quotes and the other curly.

Five quote families are tracked independently:

  - straight double:        "  ...  "
  - straight single:        '  ...  '   (skipped when adjacent to a
                                          letter — apostrophes in
                                          contractions like "don't")
  - curly double:           “  ...  ”
  - curly single:           ‘  ...  ’
  - backtick code spans:    `  ...  `   (Markdown inline code)

Single deterministic pass, no I/O, no third-party deps.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict


# Quote family -> (open char, close char). For the symmetric families
# (straight double, straight single, backtick) the open and close are
# identical and we balance by parity.
_FAMILIES = [
    ("straight_double", '"',  '"'),
    ("straight_single", "'",  "'"),
    ("curly_double",    "\u201C", "\u201D"),  # “ ”
    ("curly_single",    "\u2018", "\u2019"),  # ‘ ’
    ("backtick",        "`",  "`"),
]


class QuotationValidationError(ValueError):
    """Raised on structurally unusable input (not a string)."""


@dataclass(frozen=True)
class Finding:
    kind: str       # unbalanced_symmetric, unmatched_open, unmatched_close, mixed_pairing
    family: str
    count: int      # how many of this anomaly were found
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    ok: bool
    counts: dict     # family -> {"open": int, "close": int}
    findings: list

    def kinds(self) -> list:
        return sorted({f.kind for f in self.findings})

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "counts": self.counts,
            "findings": [f.to_dict() for f in self.findings],
        }


def _is_apostrophe(prose: str, i: int) -> bool:
    """Heuristic: a straight ' that has a letter on at least one side
    is treated as an apostrophe (don't, it's, John's), not a quote."""
    left = prose[i - 1] if i > 0 else ""
    right = prose[i + 1] if i + 1 < len(prose) else ""
    return left.isalpha() or right.isalpha()


def _count_symmetric(prose: str, ch: str, *, skip_apostrophes: bool) -> int:
    n = 0
    for i, c in enumerate(prose):
        if c != ch:
            continue
        if skip_apostrophes and ch == "'" and _is_apostrophe(prose, i):
            continue
        n += 1
    return n


def _count(prose: str, ch: str) -> int:
    return prose.count(ch)


def validate_quotation_marks(
    prose: str,
    *,
    skip_apostrophes: bool = True,
    forbid_mixed_pairing: bool = True,
) -> Report:
    """Validate quotation balance across five quote families.

    Findings:

      - **unbalanced_symmetric** (hard): odd number of straight-double,
        straight-single (after apostrophe filtering), or backtick
        characters. Symmetric quotes can only be balanced by parity.
      - **unmatched_open** / **unmatched_close** (hard): for the curly
        families, ``open_count != close_count``. Reported separately
        so the caller knows whether the model dropped an opener or a
        closer.
      - **mixed_pairing** (warn unless ``forbid_mixed_pairing=True``):
        prose contains *both* a straight-double-quote span and a
        curly-double-quote pair. Disabled-by-default for casual prose
        but useful when the output target is JSON or any other format
        that demands one canonical form.

    ``ok`` is False iff any hard finding fires (or if
    ``forbid_mixed_pairing`` flips ``mixed_pairing`` to hard).
    """
    if not isinstance(prose, str):
        raise QuotationValidationError(
            f"prose must be str, got {type(prose).__name__}")

    counts: dict = {}
    findings: list = []

    # straight double
    sd = _count(prose, '"')
    counts["straight_double"] = {"open": sd, "close": sd, "total": sd}
    if sd % 2 == 1:
        findings.append(Finding(
            kind="unbalanced_symmetric",
            family="straight_double",
            count=sd,
            detail=f'odd number of straight double quotes (\") found: {sd}',
        ))

    # straight single (apostrophe-aware)
    ss = _count_symmetric(prose, "'", skip_apostrophes=skip_apostrophes)
    counts["straight_single"] = {"open": ss, "close": ss, "total": ss}
    if ss % 2 == 1:
        findings.append(Finding(
            kind="unbalanced_symmetric",
            family="straight_single",
            count=ss,
            detail=(
                f"odd number of straight single quotes found: {ss} "
                f"(apostrophes filtered={skip_apostrophes})"
            ),
        ))

    # curly double
    cdo = _count(prose, "\u201C")
    cdc = _count(prose, "\u201D")
    counts["curly_double"] = {"open": cdo, "close": cdc, "total": cdo + cdc}
    if cdo > cdc:
        findings.append(Finding(
            kind="unmatched_open",
            family="curly_double",
            count=cdo - cdc,
            detail=f"curly double has {cdo} openers but {cdc} closers",
        ))
    elif cdc > cdo:
        findings.append(Finding(
            kind="unmatched_close",
            family="curly_double",
            count=cdc - cdo,
            detail=f"curly double has {cdc} closers but {cdo} openers",
        ))

    # curly single
    cso = _count(prose, "\u2018")
    csc = _count(prose, "\u2019")
    counts["curly_single"] = {"open": cso, "close": csc, "total": cso + csc}
    if cso > csc:
        findings.append(Finding(
            kind="unmatched_open",
            family="curly_single",
            count=cso - csc,
            detail=f"curly single has {cso} openers but {csc} closers",
        ))
    elif csc > cso:
        findings.append(Finding(
            kind="unmatched_close",
            family="curly_single",
            count=csc - cso,
            detail=f"curly single has {csc} closers but {cso} openers",
        ))

    # backtick
    bt = _count(prose, "`")
    counts["backtick"] = {"open": bt, "close": bt, "total": bt}
    if bt % 2 == 1:
        findings.append(Finding(
            kind="unbalanced_symmetric",
            family="backtick",
            count=bt,
            detail=f"odd number of backticks found: {bt}",
        ))

    # mixed pairing across straight + curly double
    if forbid_mixed_pairing:
        has_straight_double_pair = sd >= 2
        has_curly_double_pair = (cdo + cdc) >= 2
        if has_straight_double_pair and has_curly_double_pair:
            findings.append(Finding(
                kind="mixed_pairing",
                family="double",
                count=1,
                detail=(
                    "prose mixes straight and curly double-quote pairs "
                    "in a single document"
                ),
            ))

    findings.sort(key=lambda f: (f.family, f.kind))
    ok = len(findings) == 0
    return Report(ok=ok, counts=counts, findings=findings)


# --------------------------- worked cases ---------------------------

CASES = [
    ("01 clean", (
        'The agent said "hello" and the user replied "hi". '
        "It's a clean exchange."
    )),
    ("02 dropped close double", (
        'The doc says "hello world and continues without a closer.'
    )),
    ("03 curly opener without closer + apostrophe ok", (
        "The author wrote \u201Cstart of quote and never finished, "
        "but don't worry, only one issue."
    )),
    ("04 backtick odd + mixed pairing", (
        'Use the `flag option to enable it. The user said "yes" '
        "but the doc said \u201Cno\u201D."
    )),
    ("05 nested curly single + everything balanced", (
        "The teacher said \u201CRemember the phrase \u2018carpe diem\u2019 "
        "from yesterday\u201D and the class nodded."
    )),
]


def main() -> None:
    for label, prose in CASES:
        print(f"--- {label} ---")
        rep = validate_quotation_marks(prose)
        print(json.dumps(rep.to_dict(), indent=2))
        print()

    print("=== summary ===")
    for label, prose in CASES:
        rep = validate_quotation_marks(prose)
        print(f"case {label.split()[0]}: ok={rep.ok} kinds={rep.kinds()}")


if __name__ == "__main__":
    main()

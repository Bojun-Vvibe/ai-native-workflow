"""Pure stdlib citation-anchor resolution validator.

Given an LLM output that mixes a body of prose containing inline citation
anchors of the form `[N]` (or a configurable family) with an attached
ordered list of citation entries, return a structured report of every
structural mismatch that would silently corrupt downstream "open the
linked source" behaviour.

Findings (deterministic order: by kind, then by anchor id ascending):

  - unresolved_anchor    : prose says `[N]` but no citation #N is provided
  - duplicate_id         : two citation entries claim the same id N
  - unused_citation      : citation #N is provided but never referenced
                           in prose (warning by default — many drafts
                           legitimately ship a wider bibliography than
                           they cite, so the caller sets the policy)
  - non_contiguous       : citation ids skip numbers (1,2,4) — usually a
                           sign of an entry that was deleted from the
                           list but whose anchor was left in prose by
                           the model
  - empty_target         : citation #N exists but its `url` / `text` is
                           empty/whitespace
  - malformed_id         : a citation entry has a non-positive-integer
                           id, or prose contains `[0]` / `[-1]` / `[1.0]`

A structurally invalid input (citations not a list, anchor scan input
not a string) raises CitationValidationError eagerly — the rest of the
analysis would be ambiguous and the correct default is to refuse rather
than silently report an empty findings list.

Pure function. Stdlib-only. No I/O, no clocks, no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable


class CitationValidationError(ValueError):
    """Raised eagerly on structurally bad input."""


# Default anchor pattern: `[N]` where N is a positive integer.
# Caller can override (e.g. `\(\[(\d+)\]\)` for `([1])` style).
DEFAULT_ANCHOR_RE = re.compile(r"\[(\-?\d+(?:\.\d+)?)\]")


@dataclass(frozen=True)
class Finding:
    kind: str
    anchor_id: int | None  # None for malformed_id where id wasn't parseable
    detail: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "anchor_id": self.anchor_id, "detail": self.detail}


@dataclass
class CitationReport:
    findings: list[Finding] = field(default_factory=list)
    referenced_ids: list[int] = field(default_factory=list)
    provided_ids: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        # `unused_citation` and `non_contiguous` are warnings — caller
        # may treat them as failures by inspecting `kinds()`.
        hard = {
            "unresolved_anchor",
            "duplicate_id",
            "empty_target",
            "malformed_id",
        }
        return not any(f.kind in hard for f in self.findings)

    def kinds(self) -> set[str]:
        return {f.kind for f in self.findings}

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "referenced_ids": self.referenced_ids,
            "provided_ids": self.provided_ids,
            "findings": [f.to_dict() for f in self.findings],
        }


def validate_citations(
    prose: str,
    citations: list[dict],
    *,
    anchor_re: re.Pattern[str] = DEFAULT_ANCHOR_RE,
    require_contiguous: bool = True,
    flag_unused: bool = True,
) -> CitationReport:
    """Validate inline `[N]` anchors against a citations list.

    `citations` is a list of dicts shaped like
        {"id": <positive int>, "url": "...", "text": "..."}
    `url` and `text` are both treated as "target" for empty_target —
    at least one must be non-empty.
    """
    if not isinstance(prose, str):
        raise CitationValidationError(
            f"prose must be str, got {type(prose).__name__}"
        )
    if not isinstance(citations, list):
        raise CitationValidationError(
            f"citations must be list, got {type(citations).__name__}"
        )

    findings: list[Finding] = []

    # 1. Parse referenced anchors out of prose.
    referenced: list[int] = []
    seen_malformed: set[str] = set()
    for raw in anchor_re.findall(prose):
        try:
            # Reject `[1.0]`, `[0]`, `[-1]` explicitly.
            if "." in raw or raw.startswith("-"):
                if raw not in seen_malformed:
                    findings.append(
                        Finding(
                            kind="malformed_id",
                            anchor_id=None,
                            detail=f"anchor [{raw}] in prose is not a positive integer",
                        )
                    )
                    seen_malformed.add(raw)
                continue
            n = int(raw)
            if n <= 0:
                if raw not in seen_malformed:
                    findings.append(
                        Finding(
                            kind="malformed_id",
                            anchor_id=None,
                            detail=f"anchor [{raw}] in prose is not a positive integer",
                        )
                    )
                    seen_malformed.add(raw)
                continue
            referenced.append(n)
        except ValueError:
            if raw not in seen_malformed:
                findings.append(
                    Finding(
                        kind="malformed_id",
                        anchor_id=None,
                        detail=f"anchor [{raw}] in prose is not parseable as an integer",
                    )
                )
                seen_malformed.add(raw)

    # 2. Walk citations list. Validate id shape and collect duplicates.
    provided: list[int] = []
    seen_ids: dict[int, int] = {}  # id -> count
    for idx, entry in enumerate(citations):
        if not isinstance(entry, dict):
            raise CitationValidationError(
                f"citations[{idx}] must be dict, got {type(entry).__name__}"
            )
        cid_raw = entry.get("id")
        if not isinstance(cid_raw, int) or isinstance(cid_raw, bool) or cid_raw <= 0:
            findings.append(
                Finding(
                    kind="malformed_id",
                    anchor_id=None,
                    detail=f"citations[{idx}].id={cid_raw!r} is not a positive integer",
                )
            )
            continue
        cid = cid_raw
        seen_ids[cid] = seen_ids.get(cid, 0) + 1
        if seen_ids[cid] == 1:
            provided.append(cid)

        url = (entry.get("url") or "").strip()
        text = (entry.get("text") or "").strip()
        if not url and not text:
            findings.append(
                Finding(
                    kind="empty_target",
                    anchor_id=cid,
                    detail=f"citation #{cid} has empty url and text",
                )
            )

    for cid, count in seen_ids.items():
        if count > 1:
            findings.append(
                Finding(
                    kind="duplicate_id",
                    anchor_id=cid,
                    detail=f"citation id {cid} provided {count} times",
                )
            )

    # 3. Cross-check anchors vs provided ids.
    referenced_set = set(referenced)
    provided_set = set(provided)

    for n in sorted(referenced_set - provided_set):
        findings.append(
            Finding(
                kind="unresolved_anchor",
                anchor_id=n,
                detail=f"prose references [{n}] but no citation #{n} is provided",
            )
        )

    if flag_unused:
        for n in sorted(provided_set - referenced_set):
            findings.append(
                Finding(
                    kind="unused_citation",
                    anchor_id=n,
                    detail=f"citation #{n} provided but never referenced in prose",
                )
            )

    # 4. Contiguity check on provided ids only (1..max with no gaps).
    if require_contiguous and provided:
        expected = set(range(1, max(provided) + 1))
        gaps = sorted(expected - provided_set)
        for n in gaps:
            findings.append(
                Finding(
                    kind="non_contiguous",
                    anchor_id=n,
                    detail=f"citation id {n} missing from provided ids (1..{max(provided)})",
                )
            )

    # 5. Deterministic sort: (kind, anchor_id-or-(-1)).
    findings.sort(key=lambda f: (f.kind, -1 if f.anchor_id is None else f.anchor_id))

    return CitationReport(
        findings=findings,
        referenced_ids=sorted(referenced_set),
        provided_ids=sorted(provided_set),
    )


# ---------------------------------------------------------------------------
# Worked examples
# ---------------------------------------------------------------------------

def _show(label: str, report: CitationReport) -> None:
    print(f"--- {label} ---")
    print(json.dumps(report.to_dict(), indent=2, sort_keys=False))
    print()


def main() -> None:
    # Case 01: clean — every prose anchor resolves, every citation is used.
    case01_prose = (
        "The model degrades on long contexts [1], a finding corroborated "
        "by the streaming benchmark [2]."
    )
    case01_cites = [
        {"id": 1, "url": "https://example.invalid/long-ctx", "text": "Long Context Eval"},
        {"id": 2, "url": "https://example.invalid/streaming", "text": "Streaming Bench"},
    ]
    _show("01 clean", validate_citations(case01_prose, case01_cites))

    # Case 02: prose says [3] but only [1],[2] provided -> unresolved_anchor.
    #           plus citation #2 is never used -> unused_citation.
    case02_prose = "Throughput is bounded by tokenizer cost [1] and KV-cache reads [3]."
    case02_cites = [
        {"id": 1, "url": "https://example.invalid/tok", "text": "Tokenizer cost"},
        {"id": 2, "url": "https://example.invalid/unused", "text": "Never cited"},
    ]
    _show("02 unresolved + unused", validate_citations(case02_prose, case02_cites))

    # Case 03: duplicate id (#2 listed twice), and citation #2 has empty target.
    case03_prose = "See [1] and [2]."
    case03_cites = [
        {"id": 1, "url": "https://example.invalid/a", "text": "A"},
        {"id": 2, "url": "https://example.invalid/b", "text": "B"},
        {"id": 2, "url": "", "text": ""},
    ]
    _show("03 duplicate + empty_target", validate_citations(case03_prose, case03_cites))

    # Case 04: non-contiguous (1,2,4) and malformed anchor [0] in prose.
    case04_prose = "Multi-pronged claim [1], [2], [4], plus a bogus [0]."
    case04_cites = [
        {"id": 1, "url": "https://example.invalid/x", "text": "X"},
        {"id": 2, "url": "https://example.invalid/y", "text": "Y"},
        {"id": 4, "url": "https://example.invalid/z", "text": "Z"},
    ]
    _show("04 non-contiguous + malformed", validate_citations(case04_prose, case04_cites))

    # Case 05: malformed citation id (id=0) — entry rejected, [0] in prose
    # also flagged as malformed.
    case05_prose = "The bad anchor [0] should be flagged."
    case05_cites = [
        {"id": 0, "url": "https://example.invalid/bad", "text": "bad"},
        {"id": 1, "url": "https://example.invalid/ok", "text": "ok"},
    ]
    _show("05 malformed citation id", validate_citations(case05_prose, case05_cites))

    # Summary line for cron-friendly grep.
    cases = [
        ("01", validate_citations(case01_prose, case01_cites)),
        ("02", validate_citations(case02_prose, case02_cites)),
        ("03", validate_citations(case03_prose, case03_cites)),
        ("04", validate_citations(case04_prose, case04_cites)),
        ("05", validate_citations(case05_prose, case05_cites)),
    ]
    print("=== summary ===")
    for label, rep in cases:
        kinds = sorted(rep.kinds())
        print(f"case {label}: ok={rep.ok} kinds={kinds}")


if __name__ == "__main__":
    main()

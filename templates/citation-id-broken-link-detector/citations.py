"""citation-id-broken-link-detector — pure scanner.

LLM outputs (research summaries, briefs, "with sources" answers) commonly
emit Markdown-style footnote citations like `[^1]`, `[^foo]`, or numeric
inline `[1]` references that should resolve to a footnote definition
elsewhere in the same document. Common failure modes:

- citation `[^3]` is referenced in body text but never defined
- footnote `[^src-2]` is defined but never referenced (orphan)
- footnote `[^1]` is defined twice with different URLs (collision)
- citation `[^1]` is referenced 7 times — fine, dedup the *use* count

The detector is pure: no I/O, no clocks, no network. It takes the markdown
text, returns a structured `CitationReport`. Caller decides whether to
block the doc, demote it to `human_review`, or just log.

Stdlib-only. Deterministic. The detector composes with `llm-output-trust-tiers`
(`citation_report.has_broken == True` → demote one rung) and with
`agent-decision-log-format` (one log line per scanned doc).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional


# Body reference: [^foo] anywhere except at column 0 followed by ':'
# Definition:   [^foo]: <url or text>   at the start of a line
_REF_RE = re.compile(r"\[\^([A-Za-z0-9_\-]+)\]")
_DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_\-]+)\]:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


class CitationScanError(Exception):
    """Raised on structurally malformed input (not on broken citations —
    those are the *output* of the scan)."""


@dataclass(frozen=True)
class CitationReport:
    referenced_ids: tuple[str, ...]            # unique, in first-seen order
    defined_ids: tuple[str, ...]               # unique, in first-seen order
    use_counts: dict[str, int]                 # ref id -> times referenced in body
    missing_definitions: tuple[str, ...]       # referenced but never defined
    orphan_definitions: tuple[str, ...]        # defined but never referenced
    duplicate_definitions: dict[str, tuple[str, ...]]  # id -> tuple of conflicting payloads (deterministic order)
    has_broken: bool                           # any missing OR any duplicate
    summary: str                               # one-line human-readable

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict turns tuples into lists; that's fine for json
        return d


def scan(markdown: str) -> CitationReport:
    if not isinstance(markdown, str):
        raise CitationScanError(f"expected str, got {type(markdown).__name__}")

    # 1. find all definitions first; strip them from the body so a
    # definition line `[^1]: ...` does not also count as a reference.
    defs_seen: dict[str, list[str]] = {}
    def_order: list[str] = []
    for m in _DEF_RE.finditer(markdown):
        cid = m.group(1)
        payload = m.group(2)
        if cid not in defs_seen:
            defs_seen[cid] = []
            def_order.append(cid)
        defs_seen[cid].append(payload)

    body = _DEF_RE.sub("", markdown)

    # 2. count references in the body
    use_counts: dict[str, int] = {}
    ref_order: list[str] = []
    for m in _REF_RE.finditer(body):
        cid = m.group(1)
        if cid not in use_counts:
            use_counts[cid] = 0
            ref_order.append(cid)
        use_counts[cid] += 1

    referenced = tuple(ref_order)
    defined = tuple(def_order)

    missing = tuple(cid for cid in ref_order if cid not in defs_seen)
    orphans = tuple(cid for cid in def_order if cid not in use_counts)

    duplicates: dict[str, tuple[str, ...]] = {}
    for cid in def_order:
        payloads = defs_seen[cid]
        # Dedup-but-preserve-distinct-payloads check: a definition repeated
        # verbatim is harmless; distinct payloads under the same id is a
        # real collision.
        distinct = []
        seen = set()
        for p in payloads:
            if p not in seen:
                seen.add(p)
                distinct.append(p)
        if len(distinct) > 1:
            duplicates[cid] = tuple(distinct)

    has_broken = bool(missing) or bool(duplicates)

    summary = (
        f"refs={len(referenced)} defs={len(defined)} "
        f"missing={len(missing)} orphans={len(orphans)} "
        f"duplicates={len(duplicates)} has_broken={has_broken}"
    )

    return CitationReport(
        referenced_ids=referenced,
        defined_ids=defined,
        use_counts=dict(use_counts),
        missing_definitions=missing,
        orphan_definitions=orphans,
        duplicate_definitions=duplicates,
        has_broken=has_broken,
        summary=summary,
    )

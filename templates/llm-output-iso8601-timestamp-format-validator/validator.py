"""ISO-8601 timestamp format consistency validator for LLM output.

Pure stdlib. Scans LLM-emitted text for ISO-8601-shaped timestamps and
flags mixed conventions inside the same document. The bug class this
catches: an LLM that drafts a status report or audit log will silently
mix `2026-04-26T10:00:00Z`, `2026-04-26 10:00:00`, `2026-04-26T10:00`,
and `2026-04-26T10:00:00+00:00` — all *technically* parseable, but the
resulting text is not safely diffable, sortable, or copy-pasteable into a
downstream tool that expects one canonical form.

Findings (sorted by `(offset, kind, raw)`, byte-identical across runs):

  - `mixed_timezone_style`     more than one of {`Z`, `+HH:MM` / `+HHMM`,
                               `naive` (no tz)} appears in the document.
                               Reported once per *minority* occurrence so
                               the caller can grep them out.
  - `mixed_separator`          some timestamps use `T` between date and
                               time, others use a literal space. Reported
                               on every minority occurrence.
  - `seconds_precision_drift`  some timestamps include `:SS`, others
                               omit. Reported on every minority
                               occurrence.
  - `fractional_seconds_drift` some timestamps include `.fff` fractional
                               seconds, others omit. Reported on every
                               minority occurrence (independent of
                               `seconds_precision_drift`).
  - `non_iso_date_shape`       a timestamp-looking token whose date
                               portion is not `YYYY-MM-DD` (e.g.
                               `04/26/2026 10:00:00`). Always flagged,
                               not a "minority" rule.

"Minority" = the less common of the two styles in the document. Ties
break by reporting the *second*-encountered style — caller should treat
ties as a hard pick-one signal anyway. If only one style is present the
detector emits nothing for that axis, which is the desired behavior:
this template is a *consistency* gate, not a style enforcer.

Pure function over a string; no I/O, no clocks. Stdlib-only.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple


# Canonical ISO-8601 date+time. Captures groups so we can introspect.
# Date is strict YYYY-MM-DD; time is HH:MM with optional :SS, optional
# .fff, optional tz suffix (Z | +HH:MM | +HHMM | -HH:MM | -HHMM).
_ISO_LIKE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?P<sep>[T ])"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2}))?"
    r"(?:\.(?P<frac>\d{1,9}))?"
    r"(?P<tz>Z|[+\-]\d{2}:?\d{2})?"
)
# Non-ISO date-shaped tokens: `MM/DD/YYYY HH:MM[:SS]` or
# `DD-MM-YYYY HH:MM[:SS]` (both common LLM hallucinations).
_NON_ISO_DATE = re.compile(
    r"(?P<bad>\b\d{1,2}[/\-]\d{1,2}[/\-]\d{4}[T ]\d{2}:\d{2}(?::\d{2})?\b)"
)


class ValidationError(Exception):
    """Raised on malformed inputs (not on findings)."""


@dataclass(frozen=True)
class Finding:
    kind: str
    offset: int
    raw: str
    detail: str  # what makes this token the minority


def _classify_tz(tz: Optional[str]) -> str:
    if tz is None:
        return "naive"
    if tz == "Z":
        return "z_suffix"
    return "offset"


def _minority(counter: Counter, hits: List[Tuple[int, str, str]]) -> List[Tuple[int, str, str]]:
    """Return the (offset, raw, style) hits that belong to the minority style.

    `hits` is in encounter order. `counter` counts styles. Tie-break:
    drop the *first*-encountered style, keep the *second*-encountered.
    Returns [] if only one style is present in `counter`.
    """
    if len(counter) < 2:
        return []
    sorted_by_count = counter.most_common()
    top_count = sorted_by_count[0][1]
    # If the top is unique-most, minorities are everything else. If
    # tied, pick the encounter-first as majority.
    if sorted_by_count[0][1] != sorted_by_count[1][1]:
        majority_style = sorted_by_count[0][0]
    else:
        # Tied. Walk encounter order; first style seen wins majority.
        seen_order: List[str] = []
        for _, _, style in hits:
            if style not in seen_order:
                seen_order.append(style)
            if len(seen_order) == 2:
                break
        majority_style = seen_order[0]
    out = [h for h in hits if h[2] != majority_style]
    return out


def validate_timestamps(text: str) -> List[Finding]:
    """Return a sorted list of findings for ISO-8601 inconsistencies.

    Args:
      text: raw LLM output to scan.

    Returns:
      List of `Finding` sorted by `(offset, kind, raw)`. Empty list when
      every ISO-8601 timestamp follows one consistent style across all
      five axes.

    Raises:
      ValidationError: if `text` is not a `str`.
    """
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")

    findings: List[Finding] = []

    # Per-axis encounter lists: (offset, raw, style)
    tz_hits: List[Tuple[int, str, str]] = []
    sep_hits: List[Tuple[int, str, str]] = []
    sec_hits: List[Tuple[int, str, str]] = []
    frac_hits: List[Tuple[int, str, str]] = []

    tz_counter: Counter = Counter()
    sep_counter: Counter = Counter()
    sec_counter: Counter = Counter()
    frac_counter: Counter = Counter()

    for m in _ISO_LIKE.finditer(text):
        raw = m.group(0)
        offset = m.start()
        sep = m.group("sep")
        sec = m.group("second")
        frac = m.group("frac")
        tz = m.group("tz")

        tz_style = _classify_tz(tz)
        tz_hits.append((offset, raw, tz_style))
        tz_counter[tz_style] += 1

        sep_style = "T" if sep == "T" else "space"
        sep_hits.append((offset, raw, sep_style))
        sep_counter[sep_style] += 1

        sec_style = "with_sec" if sec is not None else "no_sec"
        sec_hits.append((offset, raw, sec_style))
        sec_counter[sec_style] += 1

        frac_style = "with_frac" if frac is not None else "no_frac"
        frac_hits.append((offset, raw, frac_style))
        frac_counter[frac_style] += 1

    for offset, raw, style in _minority(tz_counter, tz_hits):
        findings.append(
            Finding(
                kind="mixed_timezone_style",
                offset=offset,
                raw=raw,
                detail=f"style={style}; counts={dict(tz_counter)}",
            )
        )
    for offset, raw, style in _minority(sep_counter, sep_hits):
        findings.append(
            Finding(
                kind="mixed_separator",
                offset=offset,
                raw=raw,
                detail=f"style={style}; counts={dict(sep_counter)}",
            )
        )
    for offset, raw, style in _minority(sec_counter, sec_hits):
        findings.append(
            Finding(
                kind="seconds_precision_drift",
                offset=offset,
                raw=raw,
                detail=f"style={style}; counts={dict(sec_counter)}",
            )
        )
    for offset, raw, style in _minority(frac_counter, frac_hits):
        findings.append(
            Finding(
                kind="fractional_seconds_drift",
                offset=offset,
                raw=raw,
                detail=f"style={style}; counts={dict(frac_counter)}",
            )
        )
    for m in _NON_ISO_DATE.finditer(text):
        findings.append(
            Finding(
                kind="non_iso_date_shape",
                offset=m.start(),
                raw=m.group("bad"),
                detail="date portion is not YYYY-MM-DD",
            )
        )

    findings.sort(key=lambda f: (f.offset, f.kind, f.raw))
    return findings


def format_report(findings: List[Finding]) -> str:
    """Render findings as a deterministic plain-text report."""
    if not findings:
        return "OK: timestamp format is consistent.\n"
    lines = [f"FOUND {len(findings)} timestamp finding(s):"]
    for f in findings:
        lines.append(f"  [{f.kind}] offset={f.offset} raw={f.raw} :: {f.detail}")
    return "\n".join(lines) + "\n"

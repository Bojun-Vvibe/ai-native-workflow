"""Pure stdlib detector for numeric hallucinations in LLM output.

A "numeric hallucination" is a number that appears in the model's *output* but
does NOT appear in the *source context* the model was given (system prompt,
retrieved documents, tool results). The number looks authoritative ("47.3% of
users", "in 2019", "$1,247.50") but was fabricated — the most damaging class of
RAG bug because a JSON-schema validator can't catch it (the shape is fine, the
*content* is invented).

Pure, deterministic, stdlib-only. Returns a structured `NumericReport` so the
caller can route on `verdict` (`clean` | `partial` | `fabricated`) instead of
parsing free-form prose.

Design choices:

1. **Numeric extraction is conservative.** Recognized shapes: integers, decimals,
   percents (`47%`, `47.3%`), currency (`$1,247.50`, `$3`), years 1000-2999, and
   plain decimals. Each match canonicalizes to a `Number(value: float, unit: str)`
   where `unit ∈ {"raw", "pct", "usd", "year"}`. Currency / percent / year
   carry their unit so `47%` does NOT match a context `47` — the context said
   "47 users", the output said "47%", the unit drift is the hallucination.

2. **Comma grouping normalized.** `1,247` and `1247` compare equal. Most
   models emit one or the other inconsistently within the same response.

3. **Tolerance is exact by default**, with an optional `rel_tol` band so a
   "approximately 47.3%" output matches a context `47.31%` if the caller
   opts in. Default tolerance is 0.0 (strict) — false negatives (missing a
   real fabrication) are worse than false positives (flagging a valid round).

4. **Year-vs-integer ambiguity resolved by context.** A bare `2019` in an
   output is treated as `unit="year"` only when surrounded by year-context
   words (`in`, `since`, `during`, `circa`, `as of`). Otherwise it's `raw`.
   This stops a context `count=2019` from silently grounding an output
   `"in 2019"` claim.

5. **Allowlist via `pinned_numbers=...`.** Some numbers are universally
   safe (`100%`, `0`, `1`, page numbers like `1` `2` `3`). Caller passes the
   allowlist; default is empty so the detector errs on the side of flagging.

6. **`verdict` enum is closed**: `clean` (every output number grounded),
   `partial` (some grounded, some not — the dangerous mixed case), `fabricated`
   (NO output numbers grounded — likely the model made the whole answer up),
   `no_numbers` (output had nothing to check — distinct from `clean` so the
   caller can route a number-free answer to a different validator).

Returns `NumericReport(verdict, output_numbers, ungrounded, grounded,
context_size, summary)` where each `Number` is hashable for dedup and
`ungrounded` preserves first-seen order in the output for stable diffs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import FrozenSet, List, Tuple


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NumericConfigError(ValueError):
    """Raised at call time on bad config (negative tolerance, etc)."""


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class Number:
    """Canonical numeric value with its unit tag."""

    value: float
    unit: str  # "raw" | "pct" | "usd" | "year"

    def __str__(self) -> str:
        if self.unit == "pct":
            return f"{_fmt(self.value)}%"
        if self.unit == "usd":
            return f"${_fmt(self.value)}"
        if self.unit == "year":
            return f"{int(self.value)}"
        return _fmt(self.value)


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


@dataclass(frozen=True)
class NumericReport:
    verdict: str  # "clean" | "partial" | "fabricated" | "no_numbers"
    output_numbers: Tuple[Number, ...]
    grounded: Tuple[Number, ...]
    ungrounded: Tuple[Number, ...]
    context_size: int  # count of distinct numbers extracted from context
    summary: str


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

# Order of patterns matters: more specific shapes first so a year doesn't get
# eaten by the bare-int rule, and currency doesn't get split into `$` + int.
# Each rule produces (kind, raw_string) for the canonicalizer.

_PCT_RE = re.compile(r"(?<![A-Za-z0-9_])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*%")
_USD_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)")
_YEAR_RE = re.compile(r"(?<![A-Za-z0-9_])(1\d{3}|2\d{3})(?![0-9.%]|,\d)")
_DEC_RE = re.compile(
    r"(?<![A-Za-z0-9_$])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+)(?![0-9%])"
)

_YEAR_CONTEXT = re.compile(
    r"\b(in|since|during|circa|by|as of|until|after|before|from)\s*$",
    re.IGNORECASE,
)


def _strip_commas(s: str) -> str:
    return s.replace(",", "")


def _canonical(kind: str, raw: str) -> Number:
    if kind == "pct":
        return Number(float(_strip_commas(raw)), "pct")
    if kind == "usd":
        return Number(float(_strip_commas(raw)), "usd")
    if kind == "year":
        return Number(float(raw), "year")
    return Number(float(_strip_commas(raw)), "raw")


def extract_numbers(text: str) -> List[Number]:
    """Extract numbers from text in first-seen order, preserving units.

    Year vs raw resolution: a 4-digit number 1000-2999 is `year` ONLY when the
    immediate preceding text matches `_YEAR_CONTEXT` (e.g., `in 2019`); else
    it's a `raw` integer.
    """
    if not text:
        return []

    spans: List[Tuple[int, int, str, str]] = []  # (start, end, kind, raw)

    for m in _PCT_RE.finditer(text):
        spans.append((m.start(), m.end(), "pct", m.group(1)))
    for m in _USD_RE.finditer(text):
        spans.append((m.start(), m.end(), "usd", m.group(1)))
    for m in _YEAR_RE.finditer(text):
        prefix = text[: m.start()]
        kind = "year" if _YEAR_CONTEXT.search(prefix) else "raw"
        spans.append((m.start(), m.end(), kind, m.group(1)))
    for m in _DEC_RE.finditer(text):
        spans.append((m.start(), m.end(), "dec", m.group(1)))

    # Resolve overlaps: prefer the earliest start; on tie, longer span.
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen: List[Tuple[int, int, str, str]] = []
    last_end = -1
    for s in spans:
        if s[0] >= last_end:
            chosen.append(s)
            last_end = s[1]

    out: List[Number] = []
    seen: set = set()
    for _, _, kind, raw in chosen:
        canonical_kind = "raw" if kind == "dec" else kind
        n = _canonical(canonical_kind, raw)
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


def _matches(out_n: Number, ctx_set: FrozenSet[Number], rel_tol: float) -> bool:
    if out_n in ctx_set:
        return True
    if rel_tol <= 0:
        return False
    for c in ctx_set:
        if c.unit != out_n.unit:
            continue
        denom = max(abs(out_n.value), abs(c.value), 1e-9)
        if abs(out_n.value - c.value) / denom <= rel_tol:
            return True
    return False


def detect(
    output: str,
    context: str,
    *,
    pinned_numbers: FrozenSet[Number] = frozenset(),
    rel_tol: float = 0.0,
) -> NumericReport:
    """Return a NumericReport for `output` grounded against `context`.

    Args:
      output: model-generated text to audit.
      context: full source text the model was supposed to ground against
               (system prompt + retrieved docs + tool results, concatenated).
      pinned_numbers: caller-supplied allowlist of numbers always considered
                      grounded (`Number(100.0, "pct")`, `Number(0.0, "raw")`).
      rel_tol: relative tolerance for fuzzy match. 0.0 (default) requires exact.

    Raises:
      NumericConfigError on negative `rel_tol`.
    """
    if rel_tol < 0:
        raise NumericConfigError(f"rel_tol must be >= 0, got {rel_tol!r}")
    if not isinstance(pinned_numbers, (frozenset, set)):
        raise NumericConfigError("pinned_numbers must be a (frozen)set of Number")

    out_nums = extract_numbers(output)
    ctx_nums = extract_numbers(context)
    ctx_set: FrozenSet[Number] = frozenset(ctx_nums) | frozenset(pinned_numbers)

    if not out_nums:
        return NumericReport(
            verdict="no_numbers",
            output_numbers=(),
            grounded=(),
            ungrounded=(),
            context_size=len(ctx_nums),
            summary=f"verdict=no_numbers context_size={len(ctx_nums)}",
        )

    grounded: List[Number] = []
    ungrounded: List[Number] = []
    for n in out_nums:
        if _matches(n, ctx_set, rel_tol):
            grounded.append(n)
        else:
            ungrounded.append(n)

    if not ungrounded:
        verdict = "clean"
    elif not grounded:
        verdict = "fabricated"
    else:
        verdict = "partial"

    summary = (
        f"verdict={verdict} "
        f"output_numbers={len(out_nums)} "
        f"grounded={len(grounded)} "
        f"ungrounded={len(ungrounded)} "
        f"context_size={len(ctx_nums)}"
    )

    return NumericReport(
        verdict=verdict,
        output_numbers=tuple(out_nums),
        grounded=tuple(grounded),
        ungrounded=tuple(ungrounded),
        context_size=len(ctx_nums),
        summary=summary,
    )


__all__ = [
    "Number",
    "NumericReport",
    "NumericConfigError",
    "extract_numbers",
    "detect",
]

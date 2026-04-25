"""Pure stdlib detector for currency-symbol / currency-code mismatches in LLM output.

LLMs routinely produce text like "the price is $50 EUR" or "€50 (USD)" —
two contradictory currency markers attached to the same numeric amount.
Downstream "extract the price into a structured field" steps then pick
one or the other arbitrarily and silently corrupt the record.

This detector scans free-text output for adjacent (within `window_chars`)
pairs of (symbol, code) where the symbol's canonical code does not match
the explicit code, plus a few related failure modes that share the same
attention surface.

Findings (deterministic order: by kind, then by start offset ascending):

  - symbol_code_mismatch  : "$50 EUR"  ($ -> USD, contradicts EUR)
  - ambiguous_dollar_sign : "$50" with no code AND prose elsewhere uses
                            multiple dollar-zone codes (USD/CAD/AUD/HKD)
                            so the bare "$" can't be safely resolved
  - duplicate_currency    : "USD $50 USD" — same code repeated, often a
                            paste-merge bug from two sources
  - unknown_currency_code : "₿50 BTC" against a configurable allowlist —
                            warns when the model emits a code outside
                            the caller's accepted set (BTC accidentally
                            shipped in a fiat-only pipeline, etc.)
  - sign_position_swap    : "50$" instead of "$50" for symbols that
                            canonically prefix the amount in en-US
                            output — a classic locale-bleed signal

A structurally invalid input (text not a string) raises
CurrencyValidationError eagerly.

Pure function. Stdlib-only. No I/O, no clocks, no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


class CurrencyValidationError(ValueError):
    """Raised eagerly on structurally bad input."""


# Symbol -> canonical ISO 4217 code (the "obvious" reading).
# `$` is intentionally absent: a bare `$` is ambiguous (USD/CAD/AUD/HKD/...).
SYMBOL_TO_CODE: dict[str, str] = {
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₩": "KRW",
    "₽": "RUB",
    "₿": "BTC",
}

# Symbols that prefix the amount in en-US output. Postfix usage triggers
# a sign_position_swap finding ("50$" instead of "$50"). The euro is
# intentionally excluded — fr-FR and de-DE write "50 €" canonically and
# the detector should not fire on a legitimate locale.
PREFIX_SYMBOLS: set[str] = {"$", "£", "¥", "₹", "₩", "₿"}

# Dollar-zone codes that all share the bare `$` glyph.
DOLLAR_ZONE_CODES: set[str] = {"USD", "CAD", "AUD", "HKD", "NZD", "SGD", "MXN"}

# Default allowlist of accepted ISO codes. Caller can pass their own.
DEFAULT_ALLOWED_CODES: frozenset[str] = frozenset(
    {"USD", "EUR", "GBP", "JPY", "INR", "KRW", "RUB", "CAD", "AUD", "HKD", "CNY"}
)

# Token regexes. The amount is optional in the symbol pattern because we
# also want to catch "the bill came to $ EUR 50" shaped failures.
_AMOUNT_RE = r"\d{1,3}(?:[,_\s]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
_SYMBOL_AMOUNT_RE = re.compile(
    r"(?P<sym>[€£¥₹₩₽₿$])\s*(?P<amt>" + _AMOUNT_RE + r")"
)
_AMOUNT_SYMBOL_RE = re.compile(
    r"(?P<amt>" + _AMOUNT_RE + r")\s*(?P<sym>[€£¥₹₩₽₿$])(?!\w)"
)
_CODE_RE = re.compile(r"\b(?P<code>[A-Z]{3})\b")


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int
    snippet: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "snippet": self.snippet,
            "detail": self.detail,
        }


@dataclass
class CurrencyReport:
    findings: list[Finding] = field(default_factory=list)
    text_length: int = 0

    @property
    def ok(self) -> bool:
        hard = {
            "symbol_code_mismatch",
            "ambiguous_dollar_sign",
            "duplicate_currency",
            "sign_position_swap",
        }
        return not any(f.kind in hard for f in self.findings)

    def kinds(self) -> set[str]:
        return {f.kind for f in self.findings}

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "text_length": self.text_length,
            "findings": [f.to_dict() for f in self.findings],
        }


def _nearest_code(text: str, around_start: int, around_end: int, window: int) -> tuple[str, int, int] | None:
    """Find the nearest [A-Z]{3} code within `window` chars of an amount span."""
    left = max(0, around_start - window)
    right = min(len(text), around_end + window)
    best: tuple[str, int, int] | None = None
    best_dist = window + 1
    for m in _CODE_RE.finditer(text, left, right):
        cs, ce = m.start(), m.end()
        # distance from amount span to code span (gap in chars)
        if ce <= around_start:
            dist = around_start - ce
        elif cs >= around_end:
            dist = cs - around_end
        else:
            dist = 0
        if dist < best_dist:
            best_dist = dist
            best = (m.group("code"), cs, ce)
    return best


def detect_currency_issues(
    text: str,
    *,
    window_chars: int = 8,
    allowed_codes: frozenset[str] = DEFAULT_ALLOWED_CODES,
) -> CurrencyReport:
    if not isinstance(text, str):
        raise CurrencyValidationError(
            f"text must be str, got {type(text).__name__}"
        )

    findings: list[Finding] = []

    # First pass: collect all ISO codes mentioned anywhere.
    all_codes_in_text: list[str] = [m.group("code") for m in _CODE_RE.finditer(text)]
    dollar_zone_present = {c for c in all_codes_in_text if c in DOLLAR_ZONE_CODES}

    # Symbol-prefixed amounts.
    seen_spans: set[tuple[int, int]] = set()
    for m in _SYMBOL_AMOUNT_RE.finditer(text):
        sym = m.group("sym")
        amt = m.group("amt")
        sp_start, sp_end = m.start(), m.end()
        seen_spans.add((sp_start, sp_end))

        nearest = _nearest_code(text, sp_start, sp_end, window_chars)

        if sym == "$":
            if nearest is None:
                if len(dollar_zone_present) >= 2:
                    findings.append(
                        Finding(
                            kind="ambiguous_dollar_sign",
                            start=sp_start,
                            end=sp_end,
                            snippet=text[sp_start:sp_end],
                            detail=(
                                f"bare $ amount with no nearby code; document mentions "
                                f"{sorted(dollar_zone_present)} so $ is ambiguous"
                            ),
                        )
                    )
                continue
            code, _, _ = nearest
            if code not in DOLLAR_ZONE_CODES and code in allowed_codes:
                findings.append(
                    Finding(
                        kind="symbol_code_mismatch",
                        start=sp_start,
                        end=sp_end,
                        snippet=text[sp_start:sp_end] + " ... " + code,
                        detail=f"$ amount labeled with non-dollar-zone code {code}",
                    )
                )
            continue

        canonical = SYMBOL_TO_CODE.get(sym)
        if canonical is None:
            continue
        if nearest is not None:
            code, _, _ = nearest
            if code != canonical and code in allowed_codes:
                findings.append(
                    Finding(
                        kind="symbol_code_mismatch",
                        start=sp_start,
                        end=sp_end,
                        snippet=text[sp_start:sp_end] + " ... " + code,
                        detail=f"symbol {sym} -> {canonical} contradicts adjacent code {code}",
                    )
                )

    # Postfix-amount symbols (e.g. "50$") for prefix-canonical glyphs.
    for m in _AMOUNT_SYMBOL_RE.finditer(text):
        sp_start, sp_end = m.start(), m.end()
        if (sp_start, sp_end) in seen_spans:
            continue
        sym = m.group("sym")
        if sym in PREFIX_SYMBOLS:
            findings.append(
                Finding(
                    kind="sign_position_swap",
                    start=sp_start,
                    end=sp_end,
                    snippet=text[sp_start:sp_end],
                    detail=f"symbol {sym} appears after amount; canonical en-US position is prefix",
                )
            )

    # duplicate_currency: same ISO code repeated within window_chars on either
    # side of an amount span.
    for m in _SYMBOL_AMOUNT_RE.finditer(text):
        sp_start, sp_end = m.start(), m.end()
        left = max(0, sp_start - window_chars)
        right = min(len(text), sp_end + window_chars)
        codes_here = [
            (cm.group("code"), cm.start())
            for cm in _CODE_RE.finditer(text, left, right)
        ]
        if len(codes_here) >= 2:
            counts: dict[str, list[int]] = {}
            for code, pos in codes_here:
                counts.setdefault(code, []).append(pos)
            for code, positions in counts.items():
                if len(positions) >= 2 and code in allowed_codes:
                    findings.append(
                        Finding(
                            kind="duplicate_currency",
                            start=sp_start,
                            end=sp_end,
                            snippet=text[left:right],
                            detail=f"code {code} appears {len(positions)} times around amount",
                        )
                    )

    # unknown_currency_code: any 3-letter code in text not in allowlist.
    seen_unknown: set[str] = set()
    for code in all_codes_in_text:
        if code in allowed_codes or code in seen_unknown:
            continue
        # Only flag if the token looks currency-shaped: must be followed
        # within window_chars by a digit, or preceded within window by an
        # amount/symbol — otherwise "USD" vs random "PDF" gets confused.
        # We approximate by checking adjacency to any amount span.
        for m in _CODE_RE.finditer(text):
            if m.group("code") != code:
                continue
            cs, ce = m.start(), m.end()
            left = max(0, cs - window_chars)
            right = min(len(text), ce + window_chars)
            window_text = text[left:right]
            if re.search(_AMOUNT_RE, window_text) or any(
                s in window_text for s in SYMBOL_TO_CODE.keys()
            ) or "$" in window_text:
                findings.append(
                    Finding(
                        kind="unknown_currency_code",
                        start=cs,
                        end=ce,
                        snippet=text[cs:ce],
                        detail=f"code {code} not in allowed_codes",
                    )
                )
                seen_unknown.add(code)
                break

    findings.sort(key=lambda f: (f.kind, f.start))
    return CurrencyReport(findings=findings, text_length=len(text))


# ---------------------------------------------------------------------------
# Worked examples
# ---------------------------------------------------------------------------

def _show(label: str, report: CurrencyReport) -> None:
    print(f"--- {label} ---")
    print(json.dumps(report.to_dict(), indent=2, sort_keys=False))
    print()


def main() -> None:
    # Case 01: clean en-US output.
    case01 = "The annual subscription is $99.00 USD per seat."
    _show("01 clean USD", detect_currency_issues(case01))

    # Case 02: classic mismatch — "$50 EUR".
    case02 = "Refund issued: $50 EUR was returned to the customer."
    _show("02 symbol_code_mismatch", detect_currency_issues(case02))

    # Case 03: ambiguous bare `$` in a doc that talks about USD and CAD.
    case03 = (
        "USD pricing for North America. CAD pricing for Canada. "
        "Bundle costs $499 — confirm zone before invoicing."
    )
    _show("03 ambiguous_dollar_sign", detect_currency_issues(case03))

    # Case 04: duplicate currency code on either side of amount.
    case04 = "Net billing: USD $1,200 USD posted on Jan 4."
    _show("04 duplicate_currency", detect_currency_issues(case04))

    # Case 05: postfix symbol (sign_position_swap) + an unknown code.
    case05 = "Crypto bonus: 50$ paid out, plus 0.01 BTC pending."
    _show("05 sign_position_swap + unknown", detect_currency_issues(case05))

    # Case 06: euro symbol attached to USD code.
    case06 = "Total due: €75 USD net of tax."
    _show("06 euro vs USD", detect_currency_issues(case06))

    cases = [
        ("01", detect_currency_issues(case01)),
        ("02", detect_currency_issues(case02)),
        ("03", detect_currency_issues(case03)),
        ("04", detect_currency_issues(case04)),
        ("05", detect_currency_issues(case05)),
        ("06", detect_currency_issues(case06)),
    ]
    print("=== summary ===")
    for label, rep in cases:
        kinds = sorted(rep.kinds())
        print(f"case {label}: ok={rep.ok} kinds={kinds}")


if __name__ == "__main__":
    main()

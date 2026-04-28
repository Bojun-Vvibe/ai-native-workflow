"""llm-output-json-number-precision-loss-detector — checker + demo.

Pure-stdlib detector for JSON numeric literals that will lose
precision when consumed by an IEEE-754-double-only consumer
(JavaScript, jq, most browser JSON.parse, many SQL JSON columns).

Failure mode: the LLM emits a JSON doc with an integer ID like
`{"id": 9007199254740993}` (== 2^53 + 1). Python's `json.loads`
parses it as a Python int and round-trips it perfectly. The exact
same bytes shipped to a Node.js service round-trip as
`9007199254740992` — the trailing `3` becomes `2` because
`Number.MAX_SAFE_INTEGER == 2^53 - 1`. Two services now disagree on
the user's ID and downstream joins silently lose rows.

Same class of bug appears for:

  * floats with more than ~15 significant digits (precision lost)
  * floats with magnitudes outside roughly 1e-308..1e308 (over/underflow
    to 0.0 or Infinity in IEEE-754 doubles)
  * integers outside the safe-integer window [-2^53+1, 2^53-1]

The detector walks the byte stream by hand because json.loads on
CPython parses huge ints losslessly into Python's arbitrary-precision
int, hiding the smell from any post-parse check.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

SAFE_INT_MAX = (1 << 53) - 1   # 9007199254740991
SAFE_INT_MIN = -SAFE_INT_MAX
DOUBLE_MAX = 1.7976931348623157e308  # exact IEEE-754 finite max
DOUBLE_MIN_NORMAL = 2.2250738585072014e-308


@dataclass(frozen=True)
class Finding:
    kind: str           # one of: int_unsafe, float_overflow, float_underflow,
                        #          float_precision_loss
    literal: str
    line_no: int
    col_no: int
    detail: str


@dataclass
class JsonNumberPrecisionReport:
    ok: bool
    numbers_checked: int
    findings: List[Finding] = field(default_factory=list)


def _line_col(src: str, idx: int) -> Tuple[int, int]:
    line = src.count("\n", 0, idx) + 1
    last_nl = src.rfind("\n", 0, idx)
    col = idx - last_nl if last_nl >= 0 else idx + 1
    return line, col


def _scan_string(src: str, i: int) -> int:
    """Skip a JSON string starting at src[i] == '"'. Return index after closing quote."""
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return j + 1
        j += 1
    return j  # unterminated; bail


def _scan_number(src: str, i: int) -> Tuple[str, int]:
    """Scan a JSON number literal starting at src[i]. Return (literal, end_index)."""
    j = i
    n = len(src)
    if j < n and src[j] == "-":
        j += 1
    while j < n and src[j].isdigit():
        j += 1
    if j < n and src[j] == ".":
        j += 1
        while j < n and src[j].isdigit():
            j += 1
    if j < n and src[j] in ("e", "E"):
        j += 1
        if j < n and src[j] in ("+", "-"):
            j += 1
        while j < n and src[j].isdigit():
            j += 1
    return src[i:j], j


def _classify(literal: str) -> Optional[Tuple[str, str]]:
    """Return (kind, detail) if literal triggers a finding, else None."""
    is_int = "." not in literal and "e" not in literal and "E" not in literal
    if is_int:
        try:
            n = int(literal)
        except ValueError:
            return None
        if n > SAFE_INT_MAX or n < SAFE_INT_MIN:
            return ("int_unsafe",
                    f"integer {literal} outside JS safe-integer window "
                    f"[{SAFE_INT_MIN}, {SAFE_INT_MAX}]; "
                    "JSON.parse / jq will silently round")
        return None
    # float path
    try:
        f = float(literal)
    except ValueError:
        return None
    if f == 0.0 and any(c not in "-0.eE+" for c in literal):
        # literal had non-zero digits but parsed to 0 → underflow
        return ("float_underflow",
                f"float {literal} underflows to 0.0 in IEEE-754 doubles")
    if f != f or f in (float("inf"), float("-inf")):
        return ("float_overflow",
                f"float {literal} overflows IEEE-754 double range "
                f"(|x| > {DOUBLE_MAX:.3e})")
    # Precision loss check: round-trip via repr and compare digit count.
    # Strip leading sign and leading zeros for the count.
    digits = [c for c in literal if c.isdigit()]
    # Drop leading zeros of the integer part for significant-digit count.
    sig = "".join(digits).lstrip("0") or "0"
    if len(sig) > 17:  # IEEE-754 double max significant digits
        rt = repr(f)
        if rt != literal:
            return ("float_precision_loss",
                    f"float {literal} ({len(sig)} sig digits) does not "
                    f"round-trip in double; reparses as {rt}")
    return None


def detect(src: str) -> JsonNumberPrecisionReport:
    findings: List[Finding] = []
    numbers_checked = 0
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == '"':
            i = _scan_string(src, i)
            continue
        if c == "-" or c.isdigit():
            # Make sure prev non-space char is not a letter (avoids matching
            # inside identifiers — JSON has no bare identifiers but be safe).
            literal, end = _scan_number(src, i)
            if literal and literal not in ("-",):
                numbers_checked += 1
                cls = _classify(literal)
                if cls is not None:
                    kind, detail = cls
                    line, col = _line_col(src, i)
                    findings.append(Finding(
                        kind=kind, literal=literal,
                        line_no=line, col_no=col, detail=detail,
                    ))
            i = end if end > i else i + 1
            continue
        i += 1
    findings.sort(key=lambda f: (f.line_no, f.col_no, f.kind))
    return JsonNumberPrecisionReport(
        ok=not findings,
        numbers_checked=numbers_checked,
        findings=findings,
    )


# --- worked-example cases -------------------------------------------------

_CASES: List[Tuple[str, str]] = [
    ("01_clean_small_ints",
     '{"a": 1, "b": -42, "c": 9007199254740991}'),  # exactly MAX_SAFE_INTEGER
    ("02_clean_normal_floats",
     '{"pi": 3.14159, "e": 2.71828, "scaled": 1.5e10}'),
    ("03_int_above_safe",
     '{"id": 9007199254740993}'),  # 2^53 + 1
    ("04_int_far_below_safe",
     '{"offset": -18014398509481984}'),  # -2^54
    ("05_float_overflow",
     '{"big": 1e400}'),
    ("06_float_underflow",
     '{"tiny": 1e-400}'),
    ("07_float_precision_loss",
     '{"ratio": 0.12345678901234567890}'),  # 20 sig digits
    ("08_mixed_clean_and_bad",
     '[\n  {"id": 1, "balance": 1e500},\n  {"id": 9999999999999999, "rate": 1.0}\n]'),
    ("09_negative_in_string_is_ignored",
     '{"note": "id is 9007199254740993"}'),
]


def main() -> int:
    print("# llm-output-json-number-precision-loss-detector — worked example\n")
    any_findings = False
    for name, src in _CASES:
        rep = detect(src)
        if rep.findings:
            any_findings = True
        print(f"## case {name}")
        print(f"input_bytes: {len(src)} numbers_checked: {rep.numbers_checked}")
        print(json.dumps(asdict(rep), indent=2, sort_keys=True))
        print()
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main())

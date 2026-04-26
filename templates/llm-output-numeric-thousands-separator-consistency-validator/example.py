"""llm-output-numeric-thousands-separator-consistency-validator.

Catches the silent-corruption class where one document mixes
thousands-separator conventions in numeric literals: `1,000` in one
paragraph and `1000` in the next, or `1,000` here and `1.000` (the
European convention) two lines down. The prose reads fine but a
downstream consumer that parses these spans (a CSV emitter, a chart
generator, a financial summariser) will silently get half its inputs
wrong.

Pure function. No regex. Stdlib only. Operates on plain text — fenced
code blocks (```), inline code (`...`), and obvious URLs are skipped
so a phone number, a port range inside `code`, or a path like
`/v1.0.0/api` doesn't trip the detector.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple


class ThousandsSeparatorValidationError(ValueError):
    """Raised on bad input shape."""


@dataclass(frozen=True)
class Number:
    raw: str
    pos: int  # 0-indexed char offset into the original text
    style: str  # one of: "comma", "dot", "space", "none", "ambiguous"
    integer_part_digits: int


@dataclass(frozen=True)
class Finding:
    kind: str
    pos: int
    detail: str


@dataclass(frozen=True)
class Result:
    numbers: List[dict]
    style_counts: dict
    findings: List[dict]
    ok: bool


def _is_digit(c: str) -> bool:
    return "0" <= c <= "9"


def _mask_skipped_regions(text: str) -> List[bool]:
    """Return per-character mask: True = scan, False = skip.
    Skip fenced code blocks, inline code spans, and obvious URLs.
    """
    mask = [True] * len(text)
    n = len(text)

    # fenced code blocks: ``` or ~~~ on their own line
    lines: List[Tuple[int, int]] = []  # (start, end_exclusive)
    start = 0
    for i, c in enumerate(text):
        if c == "\n":
            lines.append((start, i))
            start = i + 1
    lines.append((start, n))

    in_fence = False
    fence_char: Optional[str] = None
    fence_len = 0
    for ls, le in lines:
        line = text[ls:le]
        stripped = line.lstrip()
        is_fence_line = False
        if stripped.startswith("```") or stripped.startswith("~~~"):
            ch = stripped[0]
            run = 0
            for c in stripped:
                if c == ch:
                    run += 1
                else:
                    break
            if run >= 3 and (not in_fence or (ch == fence_char and run >= fence_len)):
                is_fence_line = True
                if not in_fence:
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                else:
                    in_fence = False
                    fence_char = None
                    fence_len = 0
        if in_fence or is_fence_line:
            for k in range(ls, le):
                mask[k] = False

    # inline code spans (single backtick): mask `...`
    i = 0
    while i < n:
        if mask[i] and text[i] == "`":
            j = i + 1
            while j < n and text[j] != "`" and text[j] != "\n":
                j += 1
            if j < n and text[j] == "`":
                for k in range(i, j + 1):
                    mask[k] = False
                i = j + 1
                continue
        i += 1

    # URLs: starts with http:// or https://, runs to whitespace
    i = 0
    while i < n:
        if mask[i] and text.startswith("http", i):
            rest = text[i:]
            if rest.startswith("http://") or rest.startswith("https://"):
                j = i
                while j < n and not text[j].isspace():
                    j += 1
                for k in range(i, j):
                    mask[k] = False
                i = j
                continue
        i += 1

    return mask


def _classify(raw: str) -> Tuple[str, int]:
    """Classify a numeric literal.

    Returns (style, integer_part_digits). Style is one of:
    - "comma": uses comma as thousands separator (e.g. 1,000 or 1,234,567)
    - "dot":   uses dot as thousands separator (e.g. 1.000.000)
    - "space": uses non-breaking-style space (e.g. "1 000")
    - "none":  no separator and integer part is short enough to be
               unambiguous (<=3 digits, e.g. "999", "42")
    - "ambiguous": no separator but integer part is >=4 digits
                   (e.g. "1000", "12345") — caller decides whether to
                   warn based on document context.

    Decimals are detected by trailing `.NN` or `,NN` where N=1..3
    digits. The decimal half is stripped before classification.
    """
    # detect decimal tail
    body = raw
    # comma-decimal: "1.000,5" or "1000,5"
    # dot-decimal: "1,000.5" or "1000.5"
    # We classify by whether group-separator candidates (comma or dot)
    # appear at thousands boundaries.

    # strip a trailing decimal-looking tail of 1-2 chars dec sep + 1+ digits
    # but only if it's at the end and there's exactly one such separator
    # behaving as a decimal (i.e. the LAST separator with <=3 trailing digits
    # *and* total digits after it != 3 -- because exactly 3 is ambiguous).
    integer_body = body
    # Find last comma and last dot
    last_comma = body.rfind(",")
    last_dot = body.rfind(".")
    last_sep_pos = max(last_comma, last_dot)
    if last_sep_pos != -1:
        tail = body[last_sep_pos + 1:]
        if tail.isdigit() and 1 <= len(tail) <= 2:
            # definitely decimal
            integer_body = body[:last_sep_pos]
        elif tail.isdigit() and len(tail) >= 4:
            # too long to be thousands group, must be decimal
            integer_body = body[:last_sep_pos]

    # now classify integer_body
    digits = sum(1 for c in integer_body if _is_digit(c))
    has_comma = "," in integer_body
    has_dot = "." in integer_body
    has_space = " " in integer_body or "\u00a0" in integer_body

    if has_comma and not has_dot:
        return "comma", digits
    if has_dot and not has_comma:
        return "dot", digits
    if has_space:
        return "space", digits
    if has_comma and has_dot:
        # mixed inside one literal — treat as comma if last sep is dot
        # (then dots are thousands), else dot (commas are thousands).
        # rare; classify by which appears more often.
        if integer_body.count(",") > integer_body.count("."):
            return "comma", digits
        return "dot", digits
    # no separator
    if digits >= 4:
        return "ambiguous", digits
    return "none", digits


def _scan_numbers(text: str, mask: List[bool]) -> List[Number]:
    """Find numeric literals in the unmasked regions.

    A literal is a maximal run of digits, optionally interleaved with
    `,` or `.` or ` ` (when each of those is sandwiched between digits).
    Leading sign is *not* captured (we don't care about sign for the
    consistency check).
    """
    out: List[Number] = []
    n = len(text)
    i = 0
    while i < n:
        if not mask[i] or not _is_digit(text[i]):
            i += 1
            continue
        # boundary: previous char must not be a digit/letter (so we
        # don't grab the "0" inside "v1.0.0" — but URLs are already
        # masked; this also rejects "abc123")
        if i > 0:
            prev = text[i - 1]
            if prev.isalpha():
                i += 1
                continue
        start = i
        last_digit_idx = i
        i += 1
        while i < n and mask[i]:
            c = text[i]
            if _is_digit(c):
                last_digit_idx = i
                i += 1
                continue
            if c in (",", ".", " ", "\u00a0"):
                # must be followed by a digit to be part of the literal
                if i + 1 < n and mask[i + 1] and _is_digit(text[i + 1]):
                    i += 1
                    continue
            break
        raw = text[start:last_digit_idx + 1]
        # don't count single-digit literals (no separator question)
        digits_only = sum(1 for c in raw if _is_digit(c))
        if digits_only < 1:
            continue
        # don't count plain literals < 4 digits with no separators —
        # they can't be inconsistent with anything
        if "," not in raw and "." not in raw and " " not in raw and "\u00a0" not in raw and digits_only < 4:
            i = last_digit_idx + 1
            continue
        # don't count literals immediately followed by an alpha
        # (e.g. "1024px", "200ms" — those are units; the convention
        # check still applies but we want to avoid version-style noise.
        # For this template: keep them, they're still numbers.)
        style, int_digits = _classify(raw)
        out.append(Number(raw=raw, pos=start, style=style, integer_part_digits=int_digits))
        i = last_digit_idx + 1
    return out


def validate(text: str) -> Result:
    """Scan `text` for numeric literals and report any cross-document
    inconsistency in thousands-separator convention.

    Findings:
    - `mixed_styles`: more than one of {comma, dot, space} appears
      across qualifying numbers (i.e. numbers whose integer part is
      large enough to require a separator under either convention).
      Fires once per minority-style number.
    - `inconsistent_unseparated`: at least one number uses a separator
      and at least one other number with integer part >= 4 digits
      uses no separator at all. Fires once per offending unseparated
      number.
    """
    if not isinstance(text, str):
        raise ThousandsSeparatorValidationError("text must be a str")

    mask = _mask_skipped_regions(text)
    numbers = _scan_numbers(text, mask)

    style_counts: dict = {"comma": 0, "dot": 0, "space": 0, "none": 0, "ambiguous": 0}
    for num in numbers:
        style_counts[num.style] += 1

    findings: List[Finding] = []

    # determine the "dominant" separator style if any
    sep_styles = {k: style_counts[k] for k in ("comma", "dot", "space")}
    sep_used = [k for k, v in sep_styles.items() if v > 0]

    if len(sep_used) >= 2:
        # mixed convention. Pick majority as the "expected" style; flag
        # the minority entries.
        majority = max(sep_used, key=lambda k: sep_counts_get(sep_styles, k))
        for num in numbers:
            if num.style in sep_used and num.style != majority:
                findings.append(
                    Finding(
                        kind="mixed_styles",
                        pos=num.pos,
                        detail=f"{num.raw!r} uses {num.style!r} separator; document majority is {majority!r}",
                    )
                )

    # inconsistent unseparated: any "ambiguous" (no-sep, >=4 digits)
    # while at least one separator-using number exists.
    if len(sep_used) >= 1:
        for num in numbers:
            if num.style == "ambiguous":
                findings.append(
                    Finding(
                        kind="inconsistent_unseparated",
                        pos=num.pos,
                        detail=(
                            f"{num.raw!r} ({num.integer_part_digits} digits) has no separator "
                            f"but document elsewhere uses {sorted(sep_used)!r}"
                        ),
                    )
                )

    findings_sorted = sorted(
        (asdict(f) for f in findings),
        key=lambda d: (d["kind"], d["pos"], d["detail"]),
    )
    return Result(
        numbers=[asdict(num) for num in numbers],
        style_counts=style_counts,
        findings=findings_sorted,
        ok=not findings_sorted,
    )


def sep_counts_get(d: dict, k: str) -> int:
    return d.get(k, 0)


_CASES = [
    (
        "01_clean_comma_throughout",
        "Revenue grew from 1,000 to 12,500 over the year, peaking at 1,234,567 in Q4.",
    ),
    (
        "02_mixed_comma_and_unseparated",
        "We shipped 1,000 units in March and 12500 units in April. The April count is suspect.",
    ),
    (
        "03_mixed_comma_and_dot",
        "Sales were 1,234 in the US report and 1.234 in the EU report — same number, different convention.",
    ),
    (
        "04_short_numbers_dont_count",
        "There were 5 cats, 17 dogs, and 999 birds. No separator needed for any of them.",
    ),
    (
        "05_decimals_are_handled",
        "The price moved from 1,234.50 to 1,500.00, a small change. Volume hit 2,000,000 shares.",
    ),
    (
        "06_code_spans_ignored",
        "Set `port=8080` and `timeout=30000`. Real numbers in prose: we processed 1,000 events.",
    ),
    (
        "07_url_ignored",
        "See https://example.com/v1/items/12345 for the API; production handled 1,000,000 calls today.",
    ),
    (
        "08_fenced_code_ignored",
        "We hit production:\n\n```\nMAX = 100000\nMIN = 0\n```\n\nIn prose: 50,000 records were processed and 25,000 were rejected.",
    ),
]


def _main() -> None:
    print("# llm-output-numeric-thousands-separator-consistency-validator — worked example\n")
    for name, text in _CASES:
        print(f"## case {name}")
        print("text:")
        for ln in text.split("\n"):
            print(f"  | {ln}")
        result = validate(text)
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        print()


if __name__ == "__main__":
    _main()

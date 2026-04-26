"""Quote-style consistency validator for LLM prose output.

Pure stdlib, no I/O. Detects inconsistent use of smart vs straight
quotation marks within a single document.

Five finding kinds:

  - mixed_double_quote_style  some `"`, some `“`/`”`
  - mixed_single_quote_style  some `'`, some `‘`/`’` (ignoring
                              apostrophe-in-word like don't, it's)
  - unbalanced_smart_double   smart double opens != closes
  - unbalanced_smart_single   smart single opens != closes
                              (after stripping in-word apostrophes)
  - mismatched_pair           a `“` without a `”` inside the same line
                              (or vice versa) — likely paste error

The validator reports each minority occurrence individually so a
caller can grep them out by offset. "Minority" = the less frequent
of two styles in the document; ties break by reporting the
**second**-encountered style.

Public API:

    validate_quotes(text: str) -> list[Finding]
    format_report(findings: list[Finding]) -> str

Findings are sorted by (offset, kind, raw) for byte-stable output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


STRAIGHT_DOUBLE = '"'
SMART_DOUBLE_OPEN = "\u201c"   # “
SMART_DOUBLE_CLOSE = "\u201d"  # ”

STRAIGHT_SINGLE = "'"
SMART_SINGLE_OPEN = "\u2018"   # ‘
SMART_SINGLE_CLOSE = "\u2019"  # ’

# A straight single quote between two letters is treated as an
# apostrophe (don't, it's, John's) and ignored by the single-quote
# axis. Smart-single between letters is treated as a typographic
# apostrophe and likewise ignored.
_APOSTROPHE_RE = re.compile(r"(?<=[A-Za-z])['\u2019](?=[A-Za-z])")


class ValidationError(TypeError):
    """Raised when input is not a str."""


@dataclass(frozen=True)
class Finding:
    kind: str
    offset: int
    raw: str
    detail: str


def _scan_chars(text: str, charset: set[str]) -> list[tuple[int, str]]:
    return [(i, ch) for i, ch in enumerate(text) if ch in charset]


def _strip_apostrophes(text: str) -> str:
    # Replace in-word apostrophes with a neutral letter so the offsets
    # of the remaining quote characters are preserved.
    return _APOSTROPHE_RE.sub(lambda m: "X", text)


def _double_quote_findings(text: str) -> list[Finding]:
    out: list[Finding] = []
    straight = _scan_chars(text, {STRAIGHT_DOUBLE})
    smart = _scan_chars(text, {SMART_DOUBLE_OPEN, SMART_DOUBLE_CLOSE})

    n_straight = len(straight)
    n_smart = len(smart)
    if n_straight > 0 and n_smart > 0:
        # Report the minority occurrences. Tie -> report the
        # second-encountered style as minority.
        if n_straight < n_smart:
            minority, name = straight, "straight"
        elif n_smart < n_straight:
            minority, name = smart, "smart"
        else:
            # tie: pick the style of the second-encountered char overall
            second_offset = sorted(straight + smart, key=lambda x: x[0])[1][0]
            if any(o == second_offset for o, _ in straight):
                minority, name = straight, "straight"
            else:
                minority, name = smart, "smart"
        for off, ch in minority:
            out.append(
                Finding(
                    kind="mixed_double_quote_style",
                    offset=off,
                    raw=ch,
                    detail=(
                        f"style={name}; counts="
                        f"{{'straight': {n_straight}, 'smart': {n_smart}}}"
                    ),
                )
            )

    # Balance check on smart doubles (across whole document).
    opens = sum(1 for _, ch in smart if ch == SMART_DOUBLE_OPEN)
    closes = sum(1 for _, ch in smart if ch == SMART_DOUBLE_CLOSE)
    if opens != closes:
        # Report at the offset of the first smart double quote.
        first = smart[0]
        out.append(
            Finding(
                kind="unbalanced_smart_double",
                offset=first[0],
                raw=first[1],
                detail=f"open={opens} close={closes}",
            )
        )

    # Per-line mismatched pair: a smart double on a line whose pair
    # isn't on the same line.
    for line_start, line in _iter_lines(text):
        line_opens = line.count(SMART_DOUBLE_OPEN)
        line_closes = line.count(SMART_DOUBLE_CLOSE)
        if line_opens != line_closes:
            # Find the first offending char in this line.
            for j, ch in enumerate(line):
                if ch in (SMART_DOUBLE_OPEN, SMART_DOUBLE_CLOSE):
                    out.append(
                        Finding(
                            kind="mismatched_pair",
                            offset=line_start + j,
                            raw=ch,
                            detail=(
                                f"line opens={line_opens} closes={line_closes}"
                            ),
                        )
                    )
                    break

    return out


def _single_quote_findings(text: str) -> list[Finding]:
    out: list[Finding] = []
    stripped = _strip_apostrophes(text)
    straight = _scan_chars(stripped, {STRAIGHT_SINGLE})
    smart = _scan_chars(stripped, {SMART_SINGLE_OPEN, SMART_SINGLE_CLOSE})

    n_straight = len(straight)
    n_smart = len(smart)
    if n_straight > 0 and n_smart > 0:
        if n_straight < n_smart:
            minority, name = straight, "straight"
        elif n_smart < n_straight:
            minority, name = smart, "smart"
        else:
            second_offset = sorted(straight + smart, key=lambda x: x[0])[1][0]
            if any(o == second_offset for o, _ in straight):
                minority, name = straight, "straight"
            else:
                minority, name = smart, "smart"
        for off, ch in minority:
            out.append(
                Finding(
                    kind="mixed_single_quote_style",
                    offset=off,
                    raw=ch,
                    detail=(
                        f"style={name}; counts="
                        f"{{'straight': {n_straight}, 'smart': {n_smart}}}"
                    ),
                )
            )

    opens = sum(1 for _, ch in smart if ch == SMART_SINGLE_OPEN)
    closes = sum(1 for _, ch in smart if ch == SMART_SINGLE_CLOSE)
    if opens != closes:
        first = smart[0]
        out.append(
            Finding(
                kind="unbalanced_smart_single",
                offset=first[0],
                raw=first[1],
                detail=f"open={opens} close={closes}",
            )
        )
    return out


def _iter_lines(text: str):
    pos = 0
    for line in text.splitlines(keepends=False):
        yield pos, line
        pos += len(line) + 1  # assume single \n; good enough for offsets


def validate_quotes(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    findings: list[Finding] = []
    findings.extend(_double_quote_findings(text))
    findings.extend(_single_quote_findings(text))
    findings.sort(key=lambda f: (f.offset, f.kind, f.raw))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: quote style is consistent.\n"
    lines = [f"FOUND {len(findings)} quote finding(s):"]
    for f in findings:
        lines.append(
            f"  [{f.kind}] offset={f.offset} raw={f.raw!r} :: {f.detail}"
        )
    return "\n".join(lines) + "\n"

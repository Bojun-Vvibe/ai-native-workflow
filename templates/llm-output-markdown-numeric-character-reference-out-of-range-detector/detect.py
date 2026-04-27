#!/usr/bin/env python3
"""Detect HTML/markdown numeric character references whose code
point is illegal or out of range.

A numeric character reference is `&#NNN;` (decimal) or `&#xHHH;`
(hex). HTML5 specifies that several ranges are illegal and parsed
as U+FFFD:

  * code point > 0x10FFFF       (above the Unicode max)
  * code point in 0xD800..0xDFFF (UTF-16 surrogate halves)
  * code point == 0              (NULL)

LLMs producing emoji and rare glyphs frequently miscount hex
digits, e.g. emitting `&#x1F6000;` for U+1F600 (smiling face).
Such references render as a replacement character `?` in a box.

This detector is code-fence aware (skips ``` and ~~~ blocks) and
ignores inline-code spans.

Exit codes:
  0 = no findings
  1 = findings printed to stdout
  2 = usage error
"""
from __future__ import annotations

import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")

# Decimal: &#123;   Hex: &#xAF; or &#XAf;
# Per HTML5, the digits run is up to a semicolon. We require the
# semicolon here to keep the surface small and avoid false positives
# on prose like "PR #123 was merged".
NUM_REF_RE = re.compile(r"&#([xX])?([0-9A-Fa-f]+);")

UNICODE_MAX = 0x10FFFF
SURROGATE_LO = 0xD800
SURROGATE_HI = 0xDFFF


def strip_inline_code(line: str) -> str:
    out = []
    in_code = False
    for ch in line:
        if ch == "`":
            in_code = not in_code
            out.append(" ")
        elif in_code:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def classify(is_hex: bool, digits: str):
    """Return (problem_message, original_form) or (None, original)."""
    try:
        cp = int(digits, 16) if is_hex else int(digits, 10)
    except ValueError:
        # Decimal token that contained hex letters -> malformed; flag.
        return ("malformed digits", None)
    original = f"&#{'x' if is_hex else ''}{digits};"
    if cp == 0:
        return ("is NULL (parsed as U+FFFD)", original)
    if cp > UNICODE_MAX:
        return (f"is above U+10FFFF", original)
    if SURROGATE_LO <= cp <= SURROGATE_HI:
        return (f"is a UTF-16 surrogate half", original)
    return (None, original)


def scan(text: str):
    in_fence = False
    findings = []
    for i, raw in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scrubbed = strip_inline_code(raw)
        for m in NUM_REF_RE.finditer(scrubbed):
            is_hex = m.group(1) is not None
            digits = m.group(2)
            # If decimal mode but the token has any hex letter, skip:
            # the regex shouldn't have matched, but we guard anyway.
            if not is_hex and any(c not in "0123456789" for c in digits):
                continue
            problem, original = classify(is_hex, digits)
            if problem is None:
                continue
            findings.append((i, m.start(), original or m.group(0), problem))
    return findings


def main(argv):
    if len(argv) != 2:
        print("usage: detect.py <file.md>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    findings = scan(text)
    for line, col, original, problem in findings:
        print(f"{argv[1]}:{line}:{col+1}: numeric reference {original} {problem}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

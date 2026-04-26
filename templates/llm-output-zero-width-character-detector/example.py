"""Worked example: 6 cases proving the zero-width detector.

Run: ``python3 example.py``

Each case is a small string that exercises one finding kind (or the
clean-input baseline). The report rendered by ``format_report`` is the
same line-by-line output that downstream tooling will see in CI logs.
"""

from __future__ import annotations

from validator import detect_invisibles, format_report


# Build-the-string-out-of-pieces so this source file itself stays
# free of literal invisibles — the reader can verify the example by
# eye, and the test asserts on the reported codepoint, not on the
# textual content.
ZWSP = "\u200b"
ZWNJ = "\u200c"
ZWJ = "\u200d"
WJ = "\u2060"
BOM = "\ufeff"
SHY = "\u00ad"
LRO = "\u202d"  # Left-to-right override, a Trojan-Source classic.
PDI = "\u2069"  # Pop directional isolate.
INV_TIMES = "\u2062"
TAG_A = "\U000e0061"  # tag latin small letter a (U+E0061)


CASES = [
    (
        "01 clean",
        "The deploy completed at 04:00 UTC.\nAll checks passed.\n",
    ),
    (
        "02 zero_width_space inside an identifier",
        f"Set the flag {ZWSP}feature_x to true.\n",
    ),
    (
        "03 BOM at start of file plus trailing soft-hyphen",
        f"{BOM}# Postmortem\n\nIncident{SHY} response was timely.\n",
    ),
    (
        "04 trojan-source bidi run mid-sentence",
        f"if user_role == admin {LRO}// trusted{PDI} then allow.\n",
    ),
    (
        "05 multiple kinds in one line",
        f"foo{ZWJ}bar{ZWNJ}baz{WJ}qux{INV_TIMES}quux\n",
    ),
    (
        "06 invisible inside a fenced code block",
        "Here is the snippet:\n\n```python\n"
        f"x = 1{ZWSP}  # legitimate demo of zero-width space\n"
        "```\n\nEnd of doc.\n",
    ),
    (
        "07 tag-character (ASCII smuggler channel)",
        f"Looks like a normal sentence.{TAG_A} Did you notice anything?\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== case {name} ===")
        # Default settings: report everything including code-span hits.
        findings = detect_invisibles(text)
        print(format_report(findings), end="")
        # Case 06 demonstrates the suppress_in_code option.
        if name.startswith("06"):
            print("--- with suppress_in_code=True ---")
            findings2 = detect_invisibles(text, suppress_in_code=True)
            print(format_report(findings2), end="")
        print()


if __name__ == "__main__":
    main()

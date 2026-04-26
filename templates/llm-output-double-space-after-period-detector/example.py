"""Worked-example cases for `llm-output-double-space-after-period-detector`.

Run: `python3 example.py`
"""

from __future__ import annotations

from detector import detect_double_space_after_period, format_report


CASES = [
    (
        "01-clean-one-space",
        # Modern publishing convention. All single-space.
        "First sentence. Second sentence. Third sentence.\n",
    ),
    (
        "02-clean-two-space",
        # Typewriter convention, but consistent — passes.
        "First sentence.  Second sentence.  Third sentence.\n",
    ),
    (
        "03-mixed-one-and-two-space",
        # Three sentences, one-space majority, one two-space gap leaks.
        "First sentence. Second sentence.  Third sentence. Fourth sentence.\n",
    ),
    (
        "04-excess-space-3-plus",
        # 3+ spaces is never legitimate sentence spacing.
        "Heading complete.   Body begins here. Tail follows.\n",
    ),
    (
        "05-tab-after-period",
        # Tab character mid-prose is a Makefile / TSV leak.
        "End of intro.\tBody starts now. Then more body.\n",
    ),
    (
        "06-decimals-and-abbrevs-not-flagged",
        # Decimals like 3.14 and abbreviations like e.g. must NOT trigger.
        # Note: "e.g." is followed by a lowercase word, not a capital.
        "Pi is 3.14 and e.g. the next item is fine. Real sentence here. Another one.\n",
    ),
    (
        "07-mixed-with-quoted-opener",
        # Sentence boundary where the next 'word' starts with " or (.
        "First sentence. \"Quoted opener\" sentence.  (Bracketed) sentence.\n",
    ),
]


def render_input(text: str) -> str:
    """Render input with visible whitespace markers and a column ruler."""
    parts = []
    for line in text.split("\n"):
        vis = line.replace("\t", "→").replace(" ", "·")
        parts.append(f"  | {vis}")
    if parts and parts[-1] == "  | ":
        parts.pop()
    return "\n".join(parts)


def main() -> None:
    for name, text in CASES:
        print(f"=== {name} ===")
        print("input (· = space, → = tab):")
        print(render_input(text))
        findings = detect_double_space_after_period(text)
        print(format_report(findings))


if __name__ == "__main__":
    main()

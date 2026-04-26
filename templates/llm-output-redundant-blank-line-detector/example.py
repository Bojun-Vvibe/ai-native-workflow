"""Worked-example cases for `llm-output-redundant-blank-line-detector`.

Run: `python3 example.py`
"""

from __future__ import annotations

from detector import detect_redundant_blank_lines, format_report


CASES = [
    (
        "01-clean-single-blanks",
        # Single blank lines between paragraphs — canonical Markdown.
        "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n",
        {},
    ),
    (
        "02-double-blank-flagged-by-default",
        # Default `max_allowed_blanks=1` flags any run of 2 or more.
        "First paragraph.\n\n\nSecond paragraph.\n",
        {},
    ),
    (
        "03-double-blank-permissive",
        # `max_allowed_blanks=2` permits up to 2 blanks; only 3+ fires.
        "First paragraph.\n\n\nSecond paragraph.\n\n\n\nThird paragraph.\n",
        {"max_allowed_blanks": 2},
    ),
    (
        "04-leading-and-trailing-blanks",
        # Leading and trailing blank runs, plus one interior redundant run.
        "\n\nIntro line.\n\n\nBody line.\n\n\n\n",
        {},
    ),
    (
        "05-whitespace-only-blank-line",
        # The middle "blank" is actually `"   \t"` — invisible bug.
        "Heading\n\n   \t\n\nBody.\n",
        {},
    ),
    (
        "06-strict-no-blank-lines",
        # `max_allowed_blanks=0` forbids any blank line at all
        # (e.g. for compact log output).
        "log line one\n\nlog line two\nlog line three\n",
        {"max_allowed_blanks": 0},
    ),
    (
        "07-only-newlines",
        # Pathological: blob is nothing but newlines.
        "\n\n\n\n",
        {},
    ),
]


def render_input(text: str) -> str:
    """Render input text with explicit newline visualization."""
    parts = []
    for line in text.split("\n"):
        # show the line with a visible \n marker, and visualize trailing
        # tab/space so the reader can see whitespace-only blanks
        vis = line.replace("\t", "\\t")
        parts.append(f"  | {vis}\\n")
    # the split-on-\n trick produces an empty final element when the
    # blob ends with \n; trim that visual artifact
    if parts and parts[-1] == "  | \\n":
        parts[-1] = "  | "
    return "\n".join(parts)


def main() -> None:
    for name, text, kwargs in CASES:
        print(f"=== {name} ===")
        print("input:")
        print(render_input(text))
        if kwargs:
            print(f"params: {kwargs}")
        findings = detect_redundant_blank_lines(text, **kwargs)
        print(format_report(findings))


if __name__ == "__main__":
    main()

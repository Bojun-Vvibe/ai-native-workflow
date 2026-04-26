"""Worked example for the bullet-marker consistency validator."""

from __future__ import annotations

from validator import format_report, validate_bullet_markers

CASES = {
    "01-clean-dash": (
        "Status:\n"
        "\n"
        "- queued\n"
        "- ran\n"
        "- done\n"
    ),
    "02-mixed-in-single-list": (
        "Phases:\n"
        "\n"
        "- spec\n"
        "- plan\n"
        "* tasks\n"
        "- implement\n"
    ),
    "03-mixed-across-blocks": (
        "First list:\n"
        "\n"
        "- alpha\n"
        "- beta\n"
        "\n"
        "Second list:\n"
        "\n"
        "* gamma\n"
        "* delta\n"
        "\n"
        "Third list:\n"
        "\n"
        "- epsilon\n"
        "- zeta\n"
    ),
    "04-nested-marker-drift": (
        "Outline:\n"
        "\n"
        "- root one\n"
        "  - leaf 1a\n"
        "  - leaf 1b\n"
        "- root two\n"
        "  * leaf 2a\n"
        "  - leaf 2b\n"
    ),
    "05-fenced-code-is-ignored": (
        "Snippet:\n"
        "\n"
        "```\n"
        "- this is shell output, not a bullet\n"
        "* neither is this\n"
        "```\n"
        "\n"
        "Real list:\n"
        "\n"
        "- only-dash\n"
        "- still-only-dash\n"
    ),
    "06-clean-asterisk": (
        "* one\n"
        "* two\n"
        "* three\n"
    ),
}


def main() -> None:
    for name in sorted(CASES):
        text = CASES[name]
        findings = validate_bullet_markers(text)
        print(f"=== {name} ===")
        print(format_report(findings))
        print()


if __name__ == "__main__":
    main()

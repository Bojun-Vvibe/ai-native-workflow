"""Worked example for the emphasis-underscore-in-word detector.

Demonstrates that the detector flags risky intra-word underscores in
prose, ignores them inside code spans / fenced blocks / link URLs,
and special-cases Python dunders.
"""

from __future__ import annotations

from detector import detect_intra_word_underscores, format_report


CASES: dict[str, str] = {
    "01-clean-backticked-identifiers": (
        "Use the `user_id` field from the `MAX_RETRIES` constant.\n"
        "All renderers will preserve the underscores because the\n"
        "identifiers are wrapped in backticks.\n"
    ),
    "02-snake-case-in-prose": (
        "Set the user_id and the session_token before calling the\n"
        "endpoint. The MAX_RETRIES knob defaults to three.\n"
    ),
    "03-python-dunders-in-prose": (
        "Override the __init__ method to set up state, and define\n"
        "__repr__ for clean debugging output. The __slots__ attribute\n"
        "is optional.\n"
    ),
    "04-mixed-underscore-runs": (
        "The legacy column called this_is_an_old_name and the new\n"
        "one called something_a_bit_shorter both appear in the\n"
        "schema dump.\n"
    ),
    "05-fenced-code-is-ignored": (
        "Below is a code sample — the underscores inside the fence\n"
        "must NOT trigger findings:\n"
        "\n"
        "```python\n"
        "def my_function(user_id, session_token):\n"
        "    return MAX_RETRIES * user_id\n"
        "```\n"
    ),
    "06-inline-code-and-link-urls-ignored": (
        "Wrap identifiers like `user_id` in backticks. Link URLs are\n"
        "also safe: see [the doc](https://example.invalid/foo_bar_baz)\n"
        "and the autolink <https://example.invalid/spam_and_eggs>.\n"
    ),
    "07-tilde-fence-is-ignored": (
        "~~~text\n"
        "user_id session_token MAX_RETRIES\n"
        "~~~\n"
        "\n"
        "But this line outside the fence still flags: user_id.\n"
    ),
    "08-mixed-prose-and-code-on-one-line": (
        "Set user_id (use `session_token` for auth) and pass MAX_RETRIES.\n"
    ),
}


def main() -> None:
    for name, text in CASES.items():
        print(f"=== {name} ===")
        findings = detect_intra_word_underscores(text)
        print(format_report(findings))
        print()


if __name__ == "__main__":
    main()

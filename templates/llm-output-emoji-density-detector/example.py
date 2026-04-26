"""Worked-example cases for the emoji density detector.

Run: python3 example.py
"""

from validator import detect_emoji_issues, format_report


CASES = [
    (
        "01-clean",
        (
            "Daily summary:\n"
            "- shipped two templates.\n"
            "- ran the linter and fixed two findings.\n"
            "- queued the next mission.\n"
        ),
        {},
    ),
    (
        "02-cluster-pair",
        (
            "Release notes:\n"
            "- the migration finished \U0001F389\U0001F680 ahead of schedule.\n"
            "- one minor regression filed against the parser module.\n"
        ),
        {},
    ),
    (
        "03-per-line-over-cap",
        (
            "Weekly highlights:\n"
            "Wins: \U0001F4AA \U0001F389 \U0001F680 \u2728 \U0001F525 huge week!\n"
            "Plans: ship the dashboard.\n"
        ),
        {},
    ),
    (
        "04-doc-density-over-cap",
        (
            "ok \U0001F389 done \U0001F680 next \u2728 cool \U0001F525\n"
        ),
        {"per_100_words_cap": 5.0},
    ),
    (
        "05-zwj-joined-counts-as-one",
        # Family emoji: man + ZWJ + woman + ZWJ + girl, with VS16.
        (
            "Family photo: \U0001F468\u200D\U0001F469\u200D\U0001F467 attached.\n"
            "No other emoji on this line so no cluster finding.\n"
        ),
        {},
    ),
    (
        "06-emoji-then-comma-then-emoji",
        # Separated by ", and " — should NOT be a cluster.
        (
            "Recap: \U0001F389, and later \U0001F680 launched cleanly.\n"
        ),
        {},
    ),
]


def main() -> None:
    for name, blob, kwargs in CASES:
        print(f"=== {name} ===")
        print("input:")
        for raw in blob.splitlines():
            print(f"  | {raw}")
        findings = detect_emoji_issues(blob, **kwargs)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

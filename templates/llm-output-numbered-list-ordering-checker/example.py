"""Worked-example cases for the numbered-list ordering checker.

Run: python3 example.py
"""

from validator import detect_ordering_issues, format_report


CASES = [
    (
        "01-clean",
        (
            "Steps:\n"
            "1. install dependencies.\n"
            "2. run the migration.\n"
            "3. start the worker.\n"
        ),
    ),
    (
        "02-skipped-number",
        (
            "Repro:\n"
            "1. open the editor.\n"
            "2. paste the snippet.\n"
            "4. observe the crash.\n"
            "5. file the bug.\n"
        ),
    ),
    (
        "03-non-monotonic",
        (
            "Plan:\n"
            "1. write the spec.\n"
            "2. review with the team.\n"
            "2. address comments.\n"
            "3. ship.\n"
        ),
    ),
    (
        "04-bad-start",
        (
            "Punch list:\n"
            "3. fix the parser.\n"
            "4. update the docs.\n"
            "5. cut the release.\n"
        ),
    ),
    (
        "05-mixed-separator",
        (
            "Checklist:\n"
            "1. lint passes.\n"
            "2) tests pass.\n"
            "3. coverage holds.\n"
        ),
    ),
    (
        "06-fenced-list-not-scanned",
        (
            "Inside a code fence the renderer shows raw text:\n"
            "```\n"
            "1. one\n"
            "3. three\n"
            "5. five\n"
            "```\n"
            "Outside the fence:\n"
            "1. real first item.\n"
            "2. real second item.\n"
        ),
    ),
    (
        "07-nested-list-independent-counts",
        (
            "Outline:\n"
            "1. parent A.\n"
            "  1. child A.1.\n"
            "  2. child A.2.\n"
            "2. parent B.\n"
            "  1. child B.1.\n"
            "  3. child B.2 — skipped 2 here.\n"
        ),
    ),
    (
        "08-paragraph-restart",
        # Prose paragraph between two `1.` items: each is its own
        # list, so neither bad_start nor non_monotonic fires.
        (
            "First batch:\n"
            "1. alpha.\n"
            "2. beta.\n"
            "\n"
            "Some prose between the lists.\n"
            "\n"
            "Second batch:\n"
            "1. gamma.\n"
            "2. delta.\n"
        ),
    ),
]


def main() -> None:
    for name, blob in CASES:
        print(f"=== {name} ===")
        print("input:")
        for raw in blob.splitlines():
            print(f"  | {raw}")
        findings = detect_ordering_issues(blob)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

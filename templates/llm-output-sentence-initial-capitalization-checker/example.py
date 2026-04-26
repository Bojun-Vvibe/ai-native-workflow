"""Worked example for llm-output-sentence-initial-capitalization-checker."""

from validator import detect_lowercase_sentence_starts, format_report


CASES = [
    ("01 clean prose, three sentences",
     "The model returned a result. It was correct. We shipped it.\n"),

    ("02 lowercased sentence after a list",
     "The plan has two steps:\n"
     "\n"
     "- collect the inputs\n"
     "- run the validator\n"
     "\n"
     "then we publish the report.\n"),

    ("03 lowercased sentence after a code fence",
     "Run the script:\n"
     "\n"
     "```\n"
     "python3 example.py\n"
     "```\n"
     "\n"
     "this prints the report to stdout.\n"),

    ("04 allowlisted identifier (rsync) starting a sentence",
     "rsync copies files efficiently. It supports deltas.\n"),

    ("05 allowlisted identifier (iPhone) starting a sentence",
     "iPhone owners get the update first. Android owners follow.\n"),

    ("06 inline code does not count as the sentence start",
     "`x = 1` initializes the counter. It then loops.\n"),

    ("07 multiple lowercase starts in one paragraph",
     "the run failed. it then retried. it failed again.\n"),

    ("08 heading is not flagged even if lowercased",
     "## an intentionally lowercase heading\n"
     "\n"
     "But this prose sentence is fine.\n"),
]


def main() -> None:
    for label, text in CASES:
        print(f"=== case {label} ===")
        findings = detect_lowercase_sentence_starts(text)
        print(format_report(findings))
        print()


if __name__ == "__main__":
    main()

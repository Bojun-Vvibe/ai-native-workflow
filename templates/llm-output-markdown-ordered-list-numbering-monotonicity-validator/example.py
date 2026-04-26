"""Worked example for `llm-output-markdown-ordered-list-numbering-monotonicity-validator`.

Seven synthetic LLM markdown outputs covering each finding kind plus
the fence-aware and nested-list correctness checks.
"""

from __future__ import annotations

from validator import format_report, validate_ordered_list_numbering


CASES = [
    (
        "01-clean",
        "1. first\n2. second\n3. third\n",
    ),
    (
        "02-non-monotonic-skip",
        "1. first\n2. second\n4. fourth\n",
    ),
    (
        "03-bad-start",
        "3. starts at three\n4. continues\n5. continues\n",
    ),
    (
        "04-mixed-marker",
        "1. dot marker\n2) paren marker mixed in\n3. dot again\n",
    ),
    (
        "05-duplicate-index",
        "1. one\n2. two\n2. two again (copy-paste)\n3. three\n",
    ),
    (
        "06-nested-clean",
        "1. outer one\n   1. inner one-a\n   2. inner one-b\n"
        "2. outer two\n   1. inner two-a\n",
    ),
    (
        "07-fence-aware",
        "Real list:\n\n"
        "1. one\n2. two\n3. three\n\n"
        "Code sample (numbers inside fence are NOT validated):\n\n"
        "```python\n"
        "1. one\n"
        "2. two\n"
        "4. four   # intentional in the example\n"
        "```\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== {name} ===")
        print("input:")
        for line in text.splitlines():
            print(f"  | {line}")
        findings = validate_ordered_list_numbering(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

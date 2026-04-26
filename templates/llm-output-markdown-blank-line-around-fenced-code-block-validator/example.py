"""Worked example for `llm-output-markdown-blank-line-around-fenced-code-block-validator`.

Seven cases covering each finding kind plus list-item exemption and
the mismatched-fence-char body smell.
"""

from __future__ import annotations

from validator import format_report, validate_fence_blank_lines


CASES = [
    (
        "01-clean",
        "Here is a code sample:\n\n```python\nprint('hi')\n```\n\nMore prose.\n",
    ),
    (
        "02-missing-blank-before",
        "Here is a code sample:\n```python\nprint('hi')\n```\n\nMore prose.\n",
    ),
    (
        "03-missing-blank-after",
        "Here is a code sample:\n\n```python\nprint('hi')\n```\nMore prose.\n",
    ),
    (
        "04-unclosed-fence",
        "Intro paragraph.\n\n```python\nprint('hi')\nprint('bye')\n",
    ),
    (
        "05-mismatched-fence-char",
        "Intro.\n\n```python\nprint('hi')\n~~~\nprint('still in block')\n```\n\nOutro.\n",
    ),
    (
        "06-list-item-exemption",
        "Steps:\n\n- Run this command:\n  ```bash\n  ./deploy.sh\n  ```\n- Verify output.\n",
    ),
    (
        "07-double-bad",
        "Prose intro.\n```python\nprint('first')\n```\nMiddle prose with no breathing room.\n```python\nprint('second')\n```\nOutro.\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== {name} ===")
        print("input:")
        for line in text.splitlines():
            print(f"  | {line}")
        findings = validate_fence_blank_lines(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

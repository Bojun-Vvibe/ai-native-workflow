"""Worked example for `llm-output-bullet-terminal-punctuation-consistency-validator`.

Six synthetic LLM outputs:

  case 01: clean — every item ends with `.`
  case 02: mixed terminators — `.`, none, `;`
  case 03: trailing whitespace inside a clean-looking list
  case 04: empty item between two real items
  case 05: sentence-in-fragment-list — three short fragments + one
           glued multi-sentence paragraph
  case 06: inconsistent capitalization — items mixing upper/lower
           first chars

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import validate_bullets, format_report


CASES = [
    (
        "01-clean-period",
        "Daily summary:\n"
        "- shipped two templates.\n"
        "- ran the linter.\n"
        "- pushed to main.\n",
    ),
    (
        "02-mixed-terminators",
        "Open items:\n"
        "- review the migration plan.\n"
        "- ping the on-call\n"
        "- update the runbook;\n"
        "- close the ticket.\n",
    ),
    (
        "03-trailing-whitespace",
        "Checklist:\n"
        "- first item.\n"
        "- second item.   \n"
        "- third item.\n",
    ),
    (
        "04-empty-item",
        "Topics:\n"
        "- caching\n"
        "- \n"
        "- batching\n",
    ),
    (
        "05-sentence-in-fragment-list",
        "Risks:\n"
        "- flaky tests\n"
        "- stale cache\n"
        "- The deploy step occasionally fails. Retry usually works.\n"
        "- noisy alerts\n",
    ),
    (
        "06-inconsistent-capitalization",
        "Next steps:\n"
        "- Draft the spec.\n"
        "- review with the team.\n"
        "- Ship the change.\n",
    ),
]


def main() -> None:
    for case_id, text in CASES:
        print(f"=== {case_id} ===")
        print("input:")
        for line in text.splitlines():
            print(f"  | {line}")
        findings = validate_bullets(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

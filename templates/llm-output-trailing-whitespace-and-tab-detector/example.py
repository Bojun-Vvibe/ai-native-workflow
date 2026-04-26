"""Worked example for `llm-output-trailing-whitespace-and-tab-detector`.

Six synthetic LLM outputs:

  case 01: clean — no trailing ws, no stray tabs
  case 02: trailing spaces on a status-report line
  case 03: trailing tab (with trailing spaces after it) on a bullet
  case 04: stray tab in the BODY of a prose line
  case 05: mixed indent (spaces + tabs) on a single line
  case 06: trailing whitespace INSIDE a fenced code block (must be
           IGNORED for trailing axes — code may need it) but a
           trailing tab on the close fence line itself is reported

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import detect_whitespace_issues, format_report


CASES = [
    (
        "01-clean",
        "Daily summary:\n"
        "- shipped two templates.\n"
        "- ran the linter.\n",
    ),
    (
        "02-trailing-space",
        "Status:   \n"
        "- ok\n",
    ),
    (
        "03-trailing-tab",
        "Checklist:\n"
        "- first item.\n"
        "- second item.\t  \n"
        "- third item.\n",
    ),
    (
        "04-stray-tab-in-body",
        "Notes:\n"
        "The deploy step\toccasionally fails.\n",
    ),
    (
        "05-mixed-indent",
        "Outline:\n"
        " \t- nested item with mixed indent\n"
        "  - clean nested item\n",
    ),
    (
        "06-fenced-code-trailing-ws",
        "See snippet:\n"
        "```\n"
        "x = 1   \n"            # trailing spaces INSIDE fence — IGNORED
        "y = 2\n"
        "```\t\n"               # trailing tab on close fence — REPORTED
        "End.\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== {name} ===")
        print("input:")
        for line in text.splitlines():
            print(f"  | {line}")
        findings = detect_whitespace_issues(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

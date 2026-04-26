"""Worked example for `llm-output-emphasis-marker-consistency-validator`.

Six synthetic LLM outputs:

  case 01: clean — italic only with `*`, bold only with `**`
  case 02: mixed italic — three `*x*` spans + one `_y_` span
  case 03: mixed bold — two `**x**` spans + two `__y__` spans (tie:
                        majority defaults to asterisk on tie)
  case 04: unbalanced asterisk on a single line (unclosed italic)
  case 05: intraword underscore in prose (`snake_case` outside
                        a code span)
  case 06: bold-italic mismatch — two `***x***` spans + one `___y___`,
                        plus an underscore italic that survives
                        because the doc has no asterisk italic to
                        force a majority comparison

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import detect_emphasis_inconsistency, format_report


CASES = [
    (
        "01-clean",
        "Status update:\n"
        "\n"
        "The deploy is *healthy* and the **canary** is *green*.\n"
        "All **critical** alarms are *quiet*.\n",
    ),
    (
        "02-mixed-italic",
        "Notes:\n"
        "\n"
        "We saw *spike* at 04:00, *recovery* at 04:15, and *steady* by 05:00.\n"
        "The _alert_ was suppressed correctly.\n",
    ),
    (
        "03-mixed-bold",
        "Findings:\n"
        "\n"
        "**Severity** is high; **owner** is the platform team.\n"
        "The __runbook__ is current and the __escalation__ is clear.\n",
    ),
    (
        "04-unbalanced-asterisk",
        "Conclusion:\n"
        "\n"
        "The *root cause was a stale cache and we will deploy a fix today.\n",
    ),
    (
        "05-intraword-underscore",
        "Implementation note:\n"
        "\n"
        "The function snake_case_name reads from the cache.\n"
        "Inside backticks it is fine: `snake_case_name` renders verbatim.\n",
    ),
    (
        "06-bold-italic-mismatch",
        "Highlights:\n"
        "\n"
        "***Critical*** path is clear; ***owner*** is acknowledged.\n"
        "___Optional___ follow-ups are tracked in the ticket.\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== {name} ===")
        print("input:")
        for line in text.splitlines():
            print(f"  | {line}")
        findings = detect_emphasis_inconsistency(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

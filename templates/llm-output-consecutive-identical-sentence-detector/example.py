"""Worked example for `llm-output-consecutive-identical-sentence-detector`.

Six synthetic LLM outputs:

  case 01: clean — no stutter
  case 02: exact_repeat — same sentence twice in a row
  case 03: case_repeat — same sentence, capitalization differs
  case 04: near_repeat — one token swapped between adjacent sentences
  case 05: paragraph break correctly RESETS the previous-sentence
           context, so a sentence repeated across two paragraphs
           does NOT flag (legitimate rhetorical reuse)
  case 06: a hard-wrapped paragraph that stutters across the line
           wrap (proves the whitespace-collapse normalization is
           working)
"""

from __future__ import annotations

from validator import detect_stutter, format_report


CASES = [
    (
        "01-clean",
        "The deploy is healthy. We can ship the change.\n",
    ),
    (
        "02-exact-repeat",
        "The deploy is healthy. The deploy is healthy. We can ship.\n",
    ),
    (
        "03-case-repeat",
        "Reviewers were notified. reviewers were notified. Merge cleared.\n",
    ),
    (
        "04-near-repeat",
        "The migration finished at 04:00 UTC. "
        "The migration finished at 05:00 UTC.\n",
    ),
    (
        "05-paragraph-resets-context",
        "Section 1: incident summary.\n"
        "\n"
        "The deploy is healthy.\n"
        "\n"
        "Section 2: follow-up.\n"
        "\n"
        "The deploy is healthy.\n",
    ),
    (
        "06-hard-wrapped-stutter",
        "The on-call engineer paged the team and started\n"
        "the runbook. The on-call engineer paged the team\n"
        "and started the runbook. The incident was resolved.\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== {name} ===")
        print("input:")
        for line in text.splitlines():
            print(f"  | {line}")
        findings = detect_stutter(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

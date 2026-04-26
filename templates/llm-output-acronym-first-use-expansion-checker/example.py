"""Worked example for `llm-output-acronym-first-use-expansion-checker`.

Six synthetic LLM outputs:

  case 01: clean — every acronym expanded at first use
  case 02: undefined first use — `SLO` used in opening paragraph
                                 with no expansion anywhere
  case 03: never_expanded — `RPO` used three times, never expanded
                            (fires both `undefined_first_use` and
                            `never_expanded`)
  case 04: inconsistent_expansion — `LLM` expanded as two different
                                     long forms across paragraphs
  case 05: redundant_re_expansion — `SLO` defined in paragraph 1 and
                                     re-defined in paragraph 3
  case 06: lowercase_after_acronym + allowlist behavior — `SLO`
                                     introduced uppercase, then later
                                     written as `slo`; `API` appears
                                     undefined but is in the default
                                     allowlist so NOT flagged

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import detect_acronym_issues, format_report


CASES = [
    (
        "01-clean",
        "We met our service-level objective (SLO) for the quarter.\n"
        "The SLO target was 99.9 percent availability.\n"
        "Our recovery point objective (RPO) was also met.\n",
    ),
    (
        "02-undefined-first-use",
        "The SLO was met for the quarter and the team is on track.\n"
        "Owners should review the dashboard before the next review.\n",
    ),
    (
        "03-never-expanded-repeated",
        "The RPO was reviewed in the meeting.\n"
        "The RPO target is unchanged from last quarter.\n"
        "Future RPO reviews will be scheduled monthly.\n",
    ),
    (
        "04-inconsistent-expansion",
        "We use a large language model (LLM) for the summarization step.\n"
        "Later in the pipeline a second language learning module (LLM) "
        "handles the rerank.\n",
    ),
    (
        "05-redundant-re-expansion",
        "The service-level objective (SLO) was met for the quarter.\n"
        "The dashboard is healthy.\n"
        "As a reminder, the service-level objective (SLO) is the contract "
        "we publish to consumers.\n",
    ),
    (
        "06-lowercase-and-allowlist",
        "The service-level objective (SLO) was met.\n"
        "Later in the doc the slo target was reviewed by the team.\n"
        "The API is documented in the wiki.\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== {name} ===")
        print("input:")
        for line in text.splitlines():
            print(f"  | {line}")
        findings = detect_acronym_issues(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

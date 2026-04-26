"""Worked example for `llm-output-quote-style-consistency-validator`.

Six synthetic LLM outputs:

  case 01: clean — straight only, balanced
  case 02: mixed double quotes (one smart pair among straights)
  case 03: mixed single quotes (one smart pair among straights),
           apostrophes in `don't` are correctly ignored
  case 04: unbalanced smart double — one open, no close
  case 05: per-line mismatched pair — open on line 1, close on line 3
  case 06: clean smart only — balanced “…” pair, no straights

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import validate_quotes, format_report


CASES = [
    (
        "01-clean-straight",
        'The agent said "ack" and the reviewer said "ok".',
    ),
    (
        "02-mixed-double",
        'Phase A "queued", phase B "ran", phase C \u201cdone\u201d.',
    ),
    (
        "03-mixed-single-with-apostrophes",
        "It said 'first' then 'second' then \u2018third\u2019; "
        "don't conflate this with John's apostrophe.",
    ),
    (
        "04-unbalanced-smart-double",
        'The model emitted \u201cstart of quote and forgot to close it.',
    ),
    (
        "05-per-line-mismatched-pair",
        "Line one opens \u201chere\nline two is unrelated\n"
        "line three closes\u201d there.",
    ),
    (
        "06-clean-smart-only",
        "The reviewer wrote \u201cship it\u201d and moved on.",
    ),
]


def main() -> None:
    for case_id, text in CASES:
        print(f"=== {case_id} ===")
        print(f"input: {text!r}")
        findings = validate_quotes(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

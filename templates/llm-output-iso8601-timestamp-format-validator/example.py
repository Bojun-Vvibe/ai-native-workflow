"""Worked example for `llm-output-iso8601-timestamp-format-validator`.

Five synthetic LLM outputs:

  case 01: clean — every timestamp is `YYYY-MM-DDTHH:MM:SSZ`
  case 02: mixed timezone — three `Z` and one naive
  case 03: mixed separator — two `T`, one space
  case 04: seconds precision drift — three `:SS`, one without
  case 05: non-ISO US date shape `04/26/2026 10:00:00`

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import validate_timestamps, format_report


CASES = [
    (
        "01-clean",
        "Run started at 2026-04-26T10:00:00Z and ended at 2026-04-26T10:05:00Z.",
    ),
    (
        "02-mixed-timezone",
        "Tick A 2026-04-26T10:00:00Z, tick B 2026-04-26T10:01:00Z, "
        "tick C 2026-04-26T10:02:00Z, tick D 2026-04-26T10:03:00 (no tz).",
    ),
    (
        "03-mixed-separator",
        "Started 2026-04-26T10:00:00Z then 2026-04-26T10:01:00Z then "
        "2026-04-26 10:02:00Z (space sep).",
    ),
    (
        "04-seconds-precision-drift",
        "Bucket 2026-04-26T10:00:00Z 2026-04-26T10:01:00Z "
        "2026-04-26T10:02:00Z 2026-04-26T10:03Z (no seconds).",
    ),
    (
        "05-non-iso-date",
        "Mission ran on 04/26/2026 10:00:00 according to the host log.",
    ),
]


def main() -> None:
    for case_id, text in CASES:
        print(f"=== {case_id} ===")
        print(f"input: {text!r}")
        findings = validate_timestamps(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

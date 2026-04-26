"""Worked-example cases for `llm-output-mixed-line-ending-detector`.

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import detect_line_ending_issues, format_report


CASES = [
    (
        "01-clean-lf",
        "Status: ok\n- one\n- two\n",
    ),
    (
        "02-clean-crlf",
        "Status: ok\r\n- one\r\n- two\r\n",
    ),
    (
        "03-mixed-lf-and-crlf",
        "intro line\n second line\r\nthird line\nfourth line\r\n",
    ),
    (
        "04-bare-cr-classic-mac",
        "alpha\rbeta\rgamma\r",
    ),
    (
        "05-cr-leak-into-lf-blob",
        "first\nsecond\rthird\nfourth\n",
    ),
    (
        "06-trailing-no-eol",
        "headline\nbody paragraph without final newline",
    ),
]


def main() -> None:
    for name, payload in CASES:
        print(f"=== {name} ===")
        # Render the raw payload safely so the case file is itself
        # diffable: replace control bytes with their python-escape form.
        safe = payload.replace("\r", "\\r").replace("\n", "\\n\n  | ")
        print("input:")
        print(f"  | {safe}")
        findings = detect_line_ending_issues(payload)
        report = format_report(findings)
        print(report.rstrip("\n"))
        print()


if __name__ == "__main__":
    main()

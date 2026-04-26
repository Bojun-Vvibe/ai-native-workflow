"""Worked example for `llm-output-url-scheme-allowlist-validator`.

Runs the validator against five synthetic LLM outputs:

  case 01: clean — only `https://` URLs and a `mailto:` link
  case 02: a `javascript:alert(1)` smuggled into a markdown link
  case 03: a scheme-relative `//cdn.example.com/x.js` and a bare host
  case 04: a `data:text/html;base64,...` payload
  case 05: a unicode-scheme attack — Cyrillic 'p' inside `httрs://`

Prints findings for each case.

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import validate_urls, format_report, DEFAULT_ALLOW


CASES = [
    (
        "01-clean",
        "See https://example.com/docs and email us at mailto:hi@example.com for details.",
    ),
    (
        "02-javascript-smuggle",
        "Click [here](javascript:alert(1)) to confirm. Also see https://example.com.",
    ),
    (
        "03-scheme-relative-and-bare",
        "Load //cdn.example.com/x.js then visit example.com/landing for more.",
    ),
    (
        "04-data-uri",
        "The summary is at data:text/html;base64,PHA+aGk8L3A+ which inlines.",
    ),
    (
        "05-unicode-scheme-attack",
        "Open https\u0440://login.example.com to verify (\u0440 is Cyrillic).",
    ),
]


def main() -> None:
    print(f"allow-list: {sorted(DEFAULT_ALLOW)}")
    print()
    for case_id, text in CASES:
        print(f"=== {case_id} ===")
        print(f"input: {text!r}")
        findings = validate_urls(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

"""
Worked example for llm-output-ascii-control-character-leak-detector.

Run:
    python3 example.py

Output of this script is pasted verbatim into README.md.
"""

from validator import detect_controls, format_report


CASES = [
    (
        "01 clean prose",
        "The quick brown fox jumps over the lazy dog.\nNo control bytes here.\n",
    ),
    (
        "02 NUL byte inside an identifier",
        "value = parse(feature\x00_x)  # NUL embedded in name",
    ),
    (
        "03 ANSI escape sequence (color code)",
        "Result: \x1b[31mFAILED\x1b[0m on row 12.\n",
    ),
    (
        "04 BEL + BS combo (terminal-corrupting)",
        "ALERT\x07 Press \x08\x08\x08\x08\x08OK to continue.\n",
    ),
    (
        "05 form feed and vertical tab masquerading as line breaks",
        "para1\x0cpara2\x0bpara3\n",
    ),
    (
        "06 control char inside fenced code block",
        "Here is a sample:\n\n```python\nprint('a\x00b')\n```\n\nThe end.\n",
    ),
    (
        "07 DEL byte mid-word",
        "config_name = build\x7fname  # DEL here\n",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== case {name} ===")
        findings = detect_controls(text)
        print(format_report(findings))
        if name.startswith("06"):
            print("--- with suppress_in_code=True ---")
            print(format_report(detect_controls(text, suppress_in_code=True)))
        print()


if __name__ == "__main__":
    main()

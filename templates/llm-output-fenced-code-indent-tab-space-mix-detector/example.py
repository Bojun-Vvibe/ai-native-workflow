"""Worked example for llm-output-fenced-code-indent-tab-space-mix-detector."""

from validator import detect_indent_mix, format_report


CASES = [
    ("01 clean spaces-only block",
     "Here is a clean Python snippet:\n"
     "\n"
     "```python\n"
     "def add(a, b):\n"
     "    return a + b\n"
     "```\n"),

    ("02 mixed in single line (tab then spaces)",
     "Broken Python:\n"
     "\n"
     "```python\n"
     "def add(a, b):\n"
     "\t    return a + b\n"
     "```\n"),

    ("03 same block: one line tabs, next line spaces",
     "```python\n"
     "def add(a, b):\n"
     "\treturn a + b\n"
     "def sub(a, b):\n"
     "    return a - b\n"
     "```\n"),

    ("04 doc-level inconsistency across two blocks",
     "First sample:\n"
     "\n"
     "```python\n"
     "def a():\n"
     "    return 1\n"
     "```\n"
     "\n"
     "Second sample:\n"
     "\n"
     "```python\n"
     "def b():\n"
     "\treturn 2\n"
     "```\n"),

    ("05 makefile block is skipped (tabs are required)",
     "```make\n"
     "all:\n"
     "\techo hi\n"
     "    echo also-hi\n"
     "```\n"),

    ("06 prose-only document, no code blocks",
     "Just a paragraph of prose with no fenced code at all.\n"
     "Nothing to scan.\n"),
]


def main() -> None:
    for label, text in CASES:
        print(f"=== case {label} ===")
        findings = detect_indent_mix(text)
        print(format_report(findings))
        print()


if __name__ == "__main__":
    main()
